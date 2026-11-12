#!/usr/bin/env python3
"""
Grid bot en SIMULATION (paper trading) qui tourne dans le cloud via GitHub Actions.
Aucun compte, aucune clé, aucun ordre réel : il lit les prix publics de Binance
et rejoue chaque bougie de 1 minute pour savoir quels paliers auraient été touchés.

  python bot_grille.py demarrer etat.json --nom bot1 --crypto SOLUSDT --bas -10 --haut 10 --grilles 30 --invest 100 --frais 0.1
  python bot_grille.py tourner  etat.json
  python bot_grille.py arreter  etat.json --nom bot1
"""
import argparse, json, math, sys, time, urllib.request, urllib.error

HOTES = ["https://data-api.binance.vision", "https://api.binance.com", "https://api.binance.us"]
MIN = 60_000


def http_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "grid-bot-simulation"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())


def bougies(symbole, depuis_ms, maxi=6000):
    """Bougies 1 min CLÔTURÉES depuis depuis_ms (inclus)."""
    maintenant = int(time.time() * 1000)
    derniere_erreur = None
    for hote in HOTES:
        try:
            out, debut = [], depuis_ms
            while len(out) < maxi:
                url = f"{hote}/api/v3/klines?symbol={symbole}&interval=1m&limit=1000&startTime={debut}"
                p = http_json(url)
                if not p:
                    break
                for k in p:
                    if k[6] < maintenant:  # bougie clôturée
                        out.append({"t": k[0], "o": float(k[1]), "h": float(k[2]), "l": float(k[3]), "c": float(k[4])})
                if len(p) < 1000:
                    break
                debut = p[-1][0] + MIN
            return out, hote
        except Exception as e:  # hôte suivant
            derniere_erreur = e
    raise RuntimeError(f"Prix indisponibles pour {symbole} : {derniere_erreur}")


def paliers(bas, haut, n):
    return [bas * (haut / bas) ** (k / n) for k in range(n + 1)]  # géométrique


def valeur(b, prix):
    return sum(b["usdt"]) + sum(b["qte"]) * prix


def traiter_bougie(b, k):
    """Même logique que la simulation de la page : ouverture → bas → haut → clôture (ou l'inverse si rouge)."""
    f, L, n = b["frais"] / 100, b["paliers"], b["n"]
    chemin = [k["o"], k["l"], k["h"], k["c"]] if k["c"] >= k["o"] else [k["o"], k["h"], k["l"], k["c"]]
    for s in range(3):
        x, y = chemin[s], chemin[s + 1]
        if y < x:  # descente : achats sur les paliers bas
            for i in range(n):
                if not b["etat"][i] and y <= L[i] < x:
                    u = b["usdt"][i]
                    b["qte"][i] = u * (1 - f) / L[i]
                    b["cout"][i] = u
                    b["usdt"][i] = 0.0
                    b["etat"][i] = 1
                    b["frais_payes"] += u * f
                    b["journal"].append({"t": k["t"], "type": "achat", "prix": round(L[i], 10), "montant": round(u, 4)})
        elif y > x:  # montée : ventes sur les paliers hauts
            for i in range(n):
                if b["etat"][i] and x < L[i + 1] <= y:
                    brut = b["qte"][i] * L[i + 1]
                    recu = brut * (1 - f)
                    gain = recu - b["cout"][i]
                    b["encaisse"] += gain
                    b["frais_payes"] += brut * f
                    b["usdt"][i] = recu
                    b["qte"][i] = 0.0
                    b["etat"][i] = 0
                    b["cycles"] += 1
                    b["journal"].append({"t": k["t"], "type": "vente", "prix": round(L[i + 1], 10), "gain": round(gain, 4)})


def demarrer(etat, a):
    k, hote = bougies(a.crypto, int(time.time() * 1000) - 5 * MIN)
    if not k:
        raise RuntimeError("Aucun prix récent")
    p0 = k[-1]["c"]
    bas, haut = p0 * (1 + a.bas / 100), p0 * (1 + a.haut / 100)
    L = paliers(bas, haut, a.grilles)
    f, u = a.frais / 100, a.invest / a.grilles
    b = {
        "nom": a.nom, "crypto": a.crypto, "actif": True, "debut": k[-1]["t"] + MIN, "dernier": k[-1]["t"],
        "p0": p0, "bas_pct": a.bas, "haut_pct": a.haut, "n": a.grilles, "invest": a.invest, "frais": a.frais,
        "paliers": L, "etat": [], "usdt": [], "qte": [], "cout": [],
        "encaisse": 0.0, "cycles": 0, "frais_payes": 0.0, "journal": [], "historique": [],
        "qte_garder": a.invest * (1 - f) / p0, "source": hote,
    }
    for i in range(a.grilles):
        if L[i] >= p0:  # case au-dessus du prix : on achète au marché pour pouvoir revendre plus haut
            b["etat"].append(1); b["qte"].append(u * (1 - f) / p0); b["cout"].append(u); b["usdt"].append(0.0)
            b["frais_payes"] += u * f
        else:
            b["etat"].append(0); b["qte"].append(0.0); b["cout"].append(0.0); b["usdt"].append(u)
    b["prix"] = p0
    b["valeur"] = valeur(b, p0)
    b["historique"].append({"t": k[-1]["t"], "v": round(b["valeur"], 4), "p": p0})
    etat["bots"][a.nom] = b
    print(f"Démarré {a.nom} sur {a.crypto} à {p0} — fourchette {bas:.6g} → {haut:.6g}, {a.grilles} grilles")


def tourner(etat):
    for nom, b in etat["bots"].items():
        if not b.get("actif"):
            continue
        try:
            ks, hote = bougies(b["crypto"], b["dernier"] + MIN)
        except Exception as e:
            b["erreur"] = str(e)[:200]
            print(nom, "erreur", e)
            continue
        b.pop("erreur", None)
        b["source"] = hote
        for k in ks:
            traiter_bougie(b, k)
            b["dernier"] = k["t"]
            # un point d'historique par heure
            if not b["historique"] or k["t"] - b["historique"][-1]["t"] >= 3_600_000:
                b["historique"].append({"t": k["t"], "v": round(valeur(b, k["c"]), 4), "p": k["c"]})
        if ks:
            b["prix"] = ks[-1]["c"]
            b["valeur"] = valeur(b, b["prix"])
        b["journal"] = b["journal"][-150:]
        if len(b["historique"]) > 3000:
            b["historique"] = b["historique"][-3000:]
        print(f"{nom}: {len(ks)} bougies, valeur {b['valeur']:.2f} $, {b['cycles']} allers-retours")
    etat["maj"] = int(time.time() * 1000)


def arreter(etat, nom):
    b = etat["bots"].get(nom)
    if not b:
        print("Bot inconnu :", nom); return
    b["actif"] = False
    b["fin"] = int(time.time() * 1000)
    print("Arrêté", nom)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["demarrer", "tourner", "arreter"])
    ap.add_argument("fichier")
    ap.add_argument("--nom", default="bot1")
    ap.add_argument("--crypto", default="BTCUSDT")
    ap.add_argument("--bas", type=float, default=-10)
    ap.add_argument("--haut", type=float, default=10)
    ap.add_argument("--grilles", type=int, default=30)
    ap.add_argument("--invest", type=float, default=100)
    ap.add_argument("--frais", type=float, default=0.1)
    a = ap.parse_args()
    a.bas = -abs(a.bas); a.haut = abs(a.haut)
    a.nom = "".join(ch for ch in a.nom if ch.isalnum() or ch in "-_")[:30] or "bot1"
    a.crypto = a.crypto.upper().strip()
    if not a.crypto.endswith("USDT"):
        a.crypto += "USDT"
    if not (2 <= a.grilles <= 500) or a.invest <= 0 or a.bas <= -99:
        sys.exit("Réglages invalides")
    try:
        etat = json.load(open(a.fichier))
    except Exception:
        etat = {"bots": {}}
    etat.setdefault("bots", {})
    if a.action == "demarrer":
        demarrer(etat, a)
        tourner(etat)
    elif a.action == "tourner":
        tourner(etat)
    else:
        arreter(etat, a.nom)
    json.dump(etat, open(a.fichier, "w"), separators=(",", ":"))


if __name__ == "__main__":
    main()
