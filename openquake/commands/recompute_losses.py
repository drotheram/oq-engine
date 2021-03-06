#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# vim: tabstop=4 shiftwidth=4 softtabstop=4
#
# Copyright (C) 2019-2020 GEM Foundation
#
# OpenQuake is free software: you can redistribute it and/or modify it
# under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# OpenQuake is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with OpenQuake. If not, see <http://www.gnu.org/licenses/>.
import os
import logging
from openquake.baselib import sap, datastore
from openquake.commonlib import logs
from openquake.calculators.post_risk import PostRiskCalculator


@sap.Script
def recompute_losses(calc_id):
    """Re-run the postprocessing after an event based risk calculation"""
    parent = datastore.read(calc_id)
    job_id = logs.init('job', level=logging.INFO)
    if os.environ.get('OQ_DISTRIBUTE') not in ('no', 'processpool'):
        os.environ['OQ_DISTRIBUTE'] = 'processpool'
    with logs.handle(job_id, logging.INFO):
        prc = PostRiskCalculator(parent['oqparam'], job_id)
        prc.datastore.parent = parent
        prc.run()


recompute_losses.arg('calc_id', 'ID of the risk calculation', type=int)

if __name__ == '__main__':
    recompute_losses.callfunc()
