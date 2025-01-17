# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2021 Sean Anderson <seanga2@gmail.com>

import flask

from .util import get_db, get_filter_params, get_filter_clauses, get_order, get_pagination, \
                  last_modified

def logs_last_modified():
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT max(time) FROM log;")
    return last_modified(cur.fetchone()[0])

def get_logs():
    limit, offset = get_pagination()
    filters = get_filter_params()
    filter_clauses = get_filter_clauses(filters, 'title', 'league', 'format', 'map', 'time',
                                        'logid')
    order, order_clause = get_order({
        'logid': "logid",
        'duration': "duration",
        'date': "time",
	}, 'logid')
    logs = get_db().cursor()
    logs.execute("""SELECT
                        logid,
                        time,
                        duration,
                        title,
                        map,
                        format,
                        duplicate_of,
                        demoid,
                        league,
                        matchid
                    FROM log
                    JOIN map USING (mapid)
                    LEFT JOIN format USING (formatid)
                    WHERE TRUE
                        {}
                    ORDER BY {}
                    LIMIT %(limit)s OFFSET %(offset)s;""".format(filter_clauses, order_clause),
                { **filters, 'limit': limit, 'offset': offset })
    return logs

def get_players(q):
    if len(q) < 3:
        flask.abort(400, "Searches must contain at least 3 characters")

    limit, offset = get_pagination(limit=25)
    results = get_db().cursor()
    results.execute(
        """SELECT
               steamid64::TEXT,
               name,
               avatarhash,
               aliases
           FROM (SELECT
                   playerid,
                   array_agg(DISTINCT name) AS aliases,
                   max(rank) AS rank
               FROM (SELECT
                       playerid,
                       name,
                       similarity(name, %(q)s) AS rank
                   FROM name
                   JOIN player_stats USING (nameid)
                   WHERE name ILIKE %(q)s
                   ORDER BY rank DESC
               ) AS matches
               GROUP BY playerid
           ) AS matches
           JOIN player USING (playerid)
           JOIN name USING (nameid)
           WHERE last_active NOTNULL
           ORDER BY rank DESC, last_active DESC
           LIMIT %(limit)s OFFSET %(offset)s;""",
        { 'q': "%{}%".format(q), 'limit': limit, 'offset': offset})
    return results

def get_matches(compid, filters, limit=100, offset=0):
    if compid is None:
        filter_clauses = get_filter_clauses(filters, 'comp', 'divid', time='scheduled')
    else:
        filter_clauses = get_filter_clauses(filters, 'divid', time='scheduled')
        filter_clauses += "\nAND compid = %(compid)s"
    if filters['map']:
        maps = """JOIN (SELECT
                          mapid
                      FROM (SELECT
                              unnest(mapids) AS mapid
                          FROM match_semifiltered
                          GROUP BY mapid
                      ) AS maps
                      JOIN map USING (mapid)
                      WHERE map ILIKE %(map)s
                  ) AS maps ON (mapid = ANY(mapids))"""
    else:
        maps = ""
    order, order_clause = get_order({
        'round': "round_seq",
        'date': "scheduled",
        'matchid': "matchid",
    }, 'date')

    matches = get_db().cursor()
    matches.execute(
        """WITH match_semifiltered AS (SELECT *
               FROM match_pretty
               WHERE league = %(league)s
                   {0}
           ), match AS MATERIALIZED (SELECT *
               FROM match_semifiltered
               {1}
               ORDER BY {2} NULLS LAST, compid DESC, tier ASC, matchid DESC
               LIMIT %(limit)s OFFSET %(offset)s
           ) SELECT
               matchid,
               comp,
               compid,
               div,
               round,
               teamid1,
               teamid2,
               team1,
               team2,
               score1,
               score2,
               forfeit,
               maps,
               scheduled,
               logs
           FROM match
           LEFT JOIN LATERAL (SELECT
                   league,
                   matchid,
                   json_object_agg(logid, json_build_object(
                       'logid', logid,
                       'time', time,
                       'title', title,
                       'map', map,
                       'score1', CASE WHEN team1_is_red THEN red_score ELSE blue_score END,
                       'score2', CASE WHEN team1_is_red THEN blue_score ELSE red_score END,
                       'demoid', demoid
                   ) ORDER BY time DESC) AS logs
               FROM log_nodups
               LEFT JOIN format USING (formatid)
               JOIN map USING (mapid)
               WHERE league=match.league AND matchid=match.matchid
               GROUP BY league, matchid
           ) AS log USING (league, matchid)
           ORDER BY {2} NULLS LAST, compid DESC, tier ASC, matchid DESC;"""
        .format(filter_clauses, maps, order_clause),
        { **filters, 'league': flask.g.league, 'compid': compid, 'limit': limit,
          'offset': offset })
    return matches
