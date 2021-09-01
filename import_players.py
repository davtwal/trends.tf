#!/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2021 Sean Anderson <seanga2@gmail.com>

import json
import logging
import time

import requests
import psycopg2, psycopg2.extras

def get_steamids_full(c):
    last_steamid = 0
    cur = c.cursor()
    while True:
        cur.execute("""SELECT
                           steamid64
                       FROM player
                       WHERE steamid64 > %s
                       ORDER BY steamid64 ASC
                       LIMIT 100;""", (last_steamid,))
        if not cur.rowcount:
            break
        steamids = cur.fetchall()
        last_steamid = steamids[-1][0]
        yield steamids

def get_steamids_random(c):
    cur = c.cursor()
    while True:
        cur.execute("SELECT steamid64 FROM player TABLESAMPLE SYSTEM_ROWS(100);")
        yield cur.fetchall()

def create_players_parser(sub):
    players = sub.add_parser("players", help="Import players")
    players.set_defaults(importer=import_players)
    player_sub = players.add_subparsers()
    full = player_sub.add_parser("full", help="Import all players in order")
    full.set_defaults(get_steamids=get_steamids_full, wait=0)
    random = player_sub.add_parser("random", help="Import 100 random players each request")
    random.set_defaults(get_steamids=get_steamids_random, wait=1)
    players.add_argument("-k", "--key", type=str, metavar="KEY", help="Steam API key")
    players.add_argument("-w", "--wait", type=int, metavar="DELAY",
                         help="Seconds to wait between API requests")

def import_players(args, c):
    s = requests.Session()
    cur = c.cursor()
    for steamids in args.get_steamids(c):
        try:
            url = "https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/"
            params = {
                'key': args.key,
                'steamids': ','.join(str(row[0]) for row in steamids),
            }
            resp = s.get(url, params=params)
            resp.raise_for_status()
            player_info = resp.json()

            cur.execute("BEGIN;")
            psycopg2.extras.execute_values(cur, """CREATE TEMP TABLE player_update (
                                                       steamid64,
                                                       name,
                                                       avatarhash
                                                   ) ON COMMIT DROP
                                                   AS VALUES %s;""",
                                           player_info['response']['players'],
                                           "(%(steamid)s, %(personaname)s, %(avatarhash)s)")
            cur.execute("""INSERT INTO name (name)
                           SELECT
                               name
                           FROM player_update
                           ON CONFLICT DO NOTHING;""")
            cur.execute("""INSERT INTO player (steamid64, nameid, avatarhash)
                           SELECT
                               steamid64::BIGINT,
                               nameid,
                               avatarhash
                           FROM player_update
                           JOIN name USING (name)
                           ORDER BY steamid64
                           ON CONFLICT (steamid64) DO UPDATE
                           SET
                              nameid = EXCLUDED.nameid,
                              avatarhash = EXCLUDED.avatarhash;""")
            cur.execute("COMMIT;")
        except OSError as e:
            # Bail on client errors, except for rate-limiting
            if isinstance(e, requests.exceptions.HTTPError) \
               and e.resp.status_code < 500 \
               and e.resp.status_code != requests.codes.too_many:
                raise
            # Otherwise just log and try again later
            logging.exception("Could not fetch player info")
        except (ValueError, KeyError):
            logging.exception("Could not parse player info")
        except psycopg2.Error:
            logging.exception("Could not import players")

        time.sleep(args.wait)