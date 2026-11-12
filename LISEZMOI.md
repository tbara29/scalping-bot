# Trend Bot — simulation uniquement

## Mode Long terme : https://tbara29.github.io/scalping-bot/long-terme.html
- Bougies journalières, historique complet depuis 2017 (BTC ou ETH)
- Investi quand le prix est au-dessus de sa moyenne mobile (+ marge), à l'abri en dollars sinon
- Versement mensuel optionnel (épargne régulière)
- Comparaison avec « acheter et garder » : gain annuel, pire chute, année par année
- 🔬 choisit le réglage sur 2018-2021 puis le vérifie depuis 2022 (période jamais vue)
- « Signal du jour » : ce que le bot ferait aujourd'hui

## Interface mobile (v3) : https://tbara29.github.io/scalping-bot/
- Suit la tendance à la hausse ET à la baisse (vente à découvert simulée, sans effet de levier)
- Signal : pression acheteurs/vendeurs (part des achats « au marché » dans le volume Binance) + moyenne de tendance
- Stop et objectif calés sur la volatilité (ATR), sortie aussi si la tendance se retourne
- 📊 teste les réglages actuels sur 30 jours de vrais prix
- 🔬 optimiseur : choisit les réglages sur 30 jours, puis les vérifie sur les 30 jours suivants (jamais vus)
- Indice « Peur & Avidité » affiché à titre d'information

---

# Script Python (v2, scalping long uniquement)

Aucun argent réel n'est engagé : le bot ne se connecte à aucun compte.

## Installation (une fois)
1. Installer Python 3 : https://www.python.org/downloads/ (cocher « Add to PATH » sous Windows)
2. Dans un terminal : `pip install requests pandas`

## Utilisation
Mets `bot_scalping.py` dans un dossier, ouvre un terminal dans ce dossier, puis :

- **Tester sur le passé** (7 derniers jours) : `python bot_scalping.py backtest`
  Pour 30 jours : `python bot_scalping.py backtest 30`
  → affiche le résultat et crée `trades_backtest.csv` (ouvrable dans Excel)

- **Simuler en direct** : `python bot_scalping.py paper`
  → le bot suit le marché minute par minute avec 100 USDT virtuels. `Ctrl+C` pour arrêter.
  Les trades sont notés dans `journal_BTCUSDT.jsonl`.

## La stratégie
- Bougies de 5 minutes
- Achat quand la moyenne rapide (9 bougies) croise au-dessus de la lente (21 bougies), sauf si le RSI est au-dessus de 65
- Filtre de tendance : achat seulement si le prix est au-dessus de sa moyenne sur 3 h et que celle-ci monte (le bot reste dehors quand le marché baisse)
- Sortie à +1 % (gain encaissé), à -0,5 % (perte coupée) ou après 2 h
- Frais Binance (0,1 % par ordre) et glissement inclus

## Garde-fous
- -3 % sur la journée → le bot arrête jusqu'au lendemain
- 4 pertes d'affilée → pause d'1 heure

Tous les réglages sont en haut du fichier, dans `CONFIG`.

## Règle d'or
On ne passe jamais en réel tant que le bot n'est pas rentable **sur plusieurs périodes différentes en backtest ET sur au moins 4 semaines de simulation directe**.
