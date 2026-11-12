# Bot de scalping crypto — simulation uniquement

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
- Achat quand la moyenne rapide (9 min) croise au-dessus de la lente (21 min), sauf si le RSI est au-dessus de 65
- Sortie à +0,4 % (gain encaissé), à -0,3 % (perte coupée) ou après 30 min
- Frais Binance (0,1 % par ordre) et glissement inclus

## Garde-fous
- -3 % sur la journée → le bot arrête jusqu'au lendemain
- 4 pertes d'affilée → pause d'1 heure

Tous les réglages sont en haut du fichier, dans `CONFIG`.

## Règle d'or
On ne passe jamais en réel tant que le bot n'est pas rentable **sur plusieurs périodes différentes en backtest ET sur au moins 4 semaines de simulation directe**.
