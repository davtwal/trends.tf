# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2021 Sean Anderson <seanga2@gmail.com>

from .util import get_db, get_filter_params, get_filter_clauses, get_order, get_pagination

def get_logs():
    limit, offset = get_pagination()
    filters = get_filter_params()
    filter_clauses = get_filter_clauses(filters, 'title', 'format', 'map', 'time', 'logid')
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
                        duplicate_of
                    FROM log
                    JOIN map USING (mapid)
                    LEFT JOIN format USING (formatid)
                    WHERE TRUE
                        {}
                    ORDER BY {}
                    LIMIT %(limit)s OFFSET %(offset)s;""".format(filter_clauses, order_clause),
                { **filters, 'limit': limit, 'offset': offset })
    return logs
