#!/usr/bin/env python3
"""
Bot de scalping crypto — MODE SIMULATION UNIQUEMENT (aucun argent réel).

Deux modes :
  python bot_scalping.py backtest   -> teste la stratégie sur l'historique récent
  python bot_scalping.py paper      -> tourne en direct avec de l'argent virtuel

Données : API publique Binance (pas de compte, pas de clé).
Dépendances : pip install requests pandas
"""

import sys
import time
import json
from datetime import datetime, timezone

import requests
import pandas as pd

# ============================================================
# RÉGLAGES — c'est ici que tu modifies le comportement du bot
# ============================================================
CONFIG = {
    "symbole": "BTCUSDT",
    "intervalle": "5m",          # bougies de 5 minutes
    "capital_depart": 100.0,     # capital virtuel en USDT
    "part_par_trade": 0.95,      # % du capital engagé à chaque trade

    # Stratégie : croisement de moyennes mobiles + filtre RSI
    "ema_rapide": 9,
    "ema_lente": 21,
    "rsi_periode": 14,
    "rsi_max_achat": 65,         # on n'achète pas si le marché est déjà « surchauffé »
    "ema_tendance": 36,          # filtre de tendance : 36 bougies de 5 min = 3 h

    # Sortie
    "take_profit": 0.01,         # +1 % -> on encaisse
    "stop_loss": 0.005,          # -0,5 % -> on coupe la perte
    "duree_max_min": 120,        # on sort après 2 h quoi qu'il arrive

    # Coûts réels (Binance spot ~0,1 % par ordre, + glissement)
    "frais": 0.001,
    "glissement": 0.0002,

    # Garde-fous
    "perte_max_jour": 0.03,      # -3 % sur la journée -> le bot s'arrête jusqu'au lendemain
    "pertes_consecutives_max": 4,  # 4 pertes d'affilée -> pause de 60 min
    "pause_min": 60,
}

API = "https://api.binance.com/api/v3/klines"


# ------------------------------------------------------------
# Données
# ------------------------------------------------------------
def charger_bougies(symbole, intervalle, nb_bougies):
    """Télécharge les nb_bougies dernières bougies (par paquets de 1000)."""
    toutes = []
    fin = None
    while len(toutes) < nb_bougies:
        params = {"symbol": symbole, "interval": intervalle,
                  "limit": min(1000, nb_bougies - len(toutes))}
        if fin:
            params["endTime"] = fin
        r = requests.get(API, params=params, timeout=15)
        r.raise_for_status()
        paquet = r.json()
        if not paquet:
            break
        toutes = paquet + toutes
        fin = paquet[0][0] - 1
    df = pd.DataFrame(toutes, columns=[
        "t", "open", "high", "low", "close", "volume",
        "ct", "qv", "n", "tb", "tq", "x"])
    df = df[["t", "open", "high", "low", "close", "volume"]].astype(float)
    df["date"] = pd.to_datetime(df["t"], unit="ms", utc=True)
    return df.drop_duplicates("t").reset_index(drop=True)


# ------------------------------------------------------------
# Indicateurs et signal
# ------------------------------------------------------------
def ajouter_indicateurs(df, c=CONFIG):
    df = df.copy()
    df["ema_r"] = df["close"].ewm(span=c["ema_rapide"], adjust=False).mean()
    df["ema_l"] = df["close"].ewm(span=c["ema_lente"], adjust=False).mean()
    df["ema_t"] = df["close"].ewm(span=c["ema_tendance"], adjust=False).mean()
    delta = df["close"].diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / c["rsi_periode"], adjust=False).mean()
    perte = (-delta.clip(upper=0)).ewm(alpha=1 / c["rsi_periode"], adjust=False).mean()
    df["rsi"] = 100 - 100 / (1 + gain / perte.replace(0, 1e-12))
    croise = (df["ema_r"] > df["ema_l"]) & (df["ema_r"].shift(1) <= df["ema_l"].shift(1))
    tendance_ok = (df["close"] > df["ema_t"]) & (df["ema_t"] > df["ema_t"].shift(1))
    tendance_ok.iloc[:c["ema_tendance"]] = False
    df["signal_achat"] = croise & (df["rsi"] < c["rsi_max_achat"]) & tendance_ok
    return df


# ------------------------------------------------------------
# Moteur commun (backtest et simulation directe)
# ------------------------------------------------------------
class Portefeuille:
    def __init__(self, c=CONFIG):
        self.c = c
        self.capital = c["capital_depart"]
        self.position = None          # dict quand un trade est ouvert
        self.trades = []
        self.jour = None
        self.capital_debut_jour = self.capital
        self.pertes_affilee = 0
        self.pause_jusqua = None
        self.bloque_jour = False

    def _nouveau_jour(self, date):
        j = date.date()
        if j != self.jour:
            self.jour = j
            self.capital_debut_jour = self.capital
            self.bloque_jour = False

    def peut_entrer(self, date):
        self._nouveau_jour(date)
        if self.position or self.bloque_jour:
            return False
        if self.pause_jusqua and date < self.pause_jusqua:
            return False
        return True

    def entrer(self, date, prix):
        c = self.c
        prix_exec = prix * (1 + c["glissement"])
        mise = self.capital * c["part_par_trade"]
        qte = mise * (1 - c["frais"]) / prix_exec
        self.capital -= mise
        self.position = {"date": date, "prix": prix_exec, "qte": qte, "mise": mise,
                         "tp": prix_exec * (1 + c["take_profit"]),
                         "sl": prix_exec * (1 - c["stop_loss"])}

    def verifier_sortie(self, date, haut, bas, cloture):
        """Renvoie le trade fermé, ou None. Prudence : si TP et SL sont tous deux
        touchés dans la même bougie, on suppose que le SL l'a été en premier."""
        p = self.position
        if not p:
            return None
        if bas <= p["sl"]:
            return self._sortir(date, p["sl"], "stop-loss")
        if haut >= p["tp"]:
            return self._sortir(date, p["tp"], "take-profit")
        if (date - p["date"]).total_seconds() / 60 >= self.c["duree_max_min"]:
            return self._sortir(date, cloture, "durée max")
        return None

    def _sortir(self, date, prix, raison):
        c, p = self.c, self.position
        prix_exec = prix * (1 - c["glissement"])
        recu = p["qte"] * prix_exec * (1 - c["frais"])
        self.capital += recu
        pnl = recu - p["mise"]
        t = {"entree": str(p["date"]), "sortie": str(date), "raison": raison,
             "prix_entree": round(p["prix"], 2), "prix_sortie": round(prix_exec, 2),
             "pnl": round(pnl, 4), "capital": round(self.capital, 4)}
        self.trades.append(t)
        self.position = None
        # Garde-fous
        self.pertes_affilee = self.pertes_affilee + 1 if pnl < 0 else 0
        if self.pertes_affilee >= c["pertes_consecutives_max"]:
            self.pause_jusqua = date + pd.Timedelta(minutes=c["pause_min"])
            self.pertes_affilee = 0
        if self.capital <= self.capital_debut_jour * (1 - c["perte_max_jour"]):
            self.bloque_jour = True
        return t


# ------------------------------------------------------------
# Mode 1 : backtest
# ------------------------------------------------------------
def backtest(df, c=CONFIG, afficher=True):
    df = ajouter_indicateurs(df, c)
    pf = Portefeuille(c)
    for i in range(c["ema_tendance"], len(df)):
        b = df.iloc[i]
        if pf.position:
            pf.verifier_sortie(b["date"], b["high"], b["low"], b["close"])
        # Signal sur la bougie précédente, entrée à l'ouverture de celle-ci (pas de triche)
        elif df["signal_achat"].iat[i - 1] and pf.peut_entrer(b["date"]):
            pf.entrer(b["date"], b["open"])
            pf.verifier_sortie(b["date"], b["high"], b["low"], b["close"])
    if pf.position:  # clôture forcée en fin de test
        der = df.iloc[-1]
        pf._sortir(der["date"], der["close"], "fin du test")

    trades = pd.DataFrame(pf.trades)
    res = resume(trades, c, df)
    if afficher:
        imprimer_resume(res)
    return res, trades


def resume(trades, c, df):
    dep = c["capital_depart"]
    fin = trades["capital"].iloc[-1] if len(trades) else dep
    gagnants = trades[trades["pnl"] > 0] if len(trades) else trades
    perdants = trades[trades["pnl"] <= 0] if len(trades) else trades
    courbe = pd.concat([pd.Series([dep]), trades["capital"]]) if len(trades) else pd.Series([dep])
    dd = ((courbe / courbe.cummax()) - 1).min()
    frais_totaux = len(trades) * 2 * c["frais"] * dep * c["part_par_trade"]
    return {
        "periode": f"{df['date'].iloc[0]:%d/%m %H:%M} -> {df['date'].iloc[-1]:%d/%m %H:%M}",
        "variation_btc_%": round((df["close"].iloc[-1] / df["close"].iloc[0] - 1) * 100, 2),
        "nb_trades": len(trades),
        "taux_reussite_%": round(len(gagnants) / len(trades) * 100, 1) if len(trades) else 0,
        "gain_moyen": round(gagnants["pnl"].mean(), 4) if len(gagnants) else 0,
        "perte_moyenne": round(perdants["pnl"].mean(), 4) if len(perdants) else 0,
        "frais_payes_approx": round(frais_totaux, 2),
        "capital_final": round(fin, 2),
        "resultat_%": round((fin / dep - 1) * 100, 2),
        "pire_baisse_%": round(dd * 100, 2),
    }


def imprimer_resume(r):
    print("\n========== RÉSULTAT DU BACKTEST ==========")
    for k, v in r.items():
        print(f"  {k:<22} {v}")
    verdict = "RENTABLE sur cette période" if r["resultat_%"] > 0 else "PERDANT sur cette période"
    print(f"\n  Verdict : {verdict}")
    print("  (Un seul backtest positif ne prouve rien : teste plusieurs périodes.)")
    print("==========================================\n")


# ------------------------------------------------------------
# Mode 2 : simulation en direct (paper trading)
# ------------------------------------------------------------
def paper(c=CONFIG):
    pf = Portefeuille(c)
    journal = f"journal_{c['symbole']}.jsonl"
    print(f"Simulation en direct sur {c['symbole']} — capital virtuel {pf.capital} USDT")
    print("Ctrl+C pour arrêter.\n")
    dernier = None
    try:
        while True:
            df = ajouter_indicateurs(charger_bougies(c["symbole"], c["intervalle"], 200), c)
            df = df.iloc[:-1]                    # on ignore la bougie encore en cours
            b = df.iloc[-1]
            if b["t"] != dernier:
                dernier = b["t"]
                maintenant = b["date"]
                if pf.position:
                    t = pf.verifier_sortie(maintenant, b["high"], b["low"], b["close"])
                    if t:
                        print(f"[{maintenant:%H:%M}] SORTIE {t['raison']:<12} "
                              f"P&L {t['pnl']:+.4f}  capital {t['capital']:.2f}")
                        with open(journal, "a") as f:
                            f.write(json.dumps(t) + "\n")
                elif b["signal_achat"] and pf.peut_entrer(maintenant):
                    pf.entrer(maintenant, b["close"])
                    print(f"[{maintenant:%H:%M}] ACHAT à {pf.position['prix']:.2f}  "
                          f"(TP {pf.position['tp']:.2f} / SL {pf.position['sl']:.2f})")
                else:
                    etat = "pause" if (pf.bloque_jour or (pf.pause_jusqua and maintenant < pf.pause_jusqua)) else "attente"
                    print(f"[{maintenant:%H:%M}] {etat:<8} prix {b['close']:.2f}  RSI {b['rsi']:.0f}  "
                          f"capital {pf.capital + (pf.position['mise'] if pf.position else 0):.2f}")
            time.sleep(15)
    except KeyboardInterrupt:
        print(f"\nArrêt. {len(pf.trades)} trades, capital {pf.capital:.2f} USDT. Journal : {journal}")


# ------------------------------------------------------------
if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "backtest"
    if mode == "backtest":
        jours = int(sys.argv[2]) if len(sys.argv) > 2 else 7
        print(f"Téléchargement de {jours} jours de bougies {CONFIG['intervalle']}...")
        data = charger_bougies(CONFIG["symbole"], CONFIG["intervalle"], jours * 288)
        res, trades = backtest(data)
        trades.to_csv("trades_backtest.csv", index=False)
        print("Détail des trades : trades_backtest.csv")
    elif mode == "paper":
        paper()
    else:
        print(__doc__)
