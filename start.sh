#!/bin/bash
# Subir o motor principal em segundo plano
python arbitrage_bot.py &

# Subir o Sniper Meme da Base em primeiro plano
python base_meme_sniper.py