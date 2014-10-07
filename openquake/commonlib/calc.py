#  -*- coding: utf-8 -*-
#  vim: tabstop=4 shiftwidth=4 softtabstop=4

#  Copyright (c) 2014, GEM Foundation

#  OpenQuake is free software: you can redistribute it and/or modify it
#  under the terms of the GNU Affero General Public License as published
#  by the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

#  OpenQuake is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.

#  You should have received a copy of the GNU Affero General Public License
#  along with OpenQuake.  If not, see <http://www.gnu.org/licenses/>.

import collections
import itertools
import operator

import numpy

from openquake.hazardlib.imt import from_string
from openquake.hazardlib.calc import gmf, filters
from openquake.hazardlib.site import SiteCollection
from openquake.risklib import scientific, workflows

from openquake.commonlib.parallel import apply_reduce
from openquake.commonlib.readinput import get_gsim, get_rupture, \
    get_sitecol_assets, get_risk_models


SourceRuptureSites = collections.namedtuple(
    'SourceRuptureSites',
    'source rupture sites')


def gen_ruptures(sources, site_coll, maximum_distance, monitor):
    """
    Yield (source, rupture, affected_sites) for each rupture
    generated by the given sources.

    :param sources: a sequence of sources
    :param site_coll: a SiteCollection instance
    :param maximum_distance: the maximum distance
    :param monitor: a Monitor object
    """
    filtsources_mon = monitor.copy('filtering sources')
    genruptures_mon = monitor.copy('generating ruptures')
    filtruptures_mon = monitor.copy('filtering ruptures')
    for src in sources:
        with filtsources_mon:
            s_sites = src.filter_sites_by_distance_to_source(
                maximum_distance, site_coll)
            if s_sites is None:
                continue

        with genruptures_mon:
            ruptures = list(src.iter_ruptures())
        if not ruptures:
            continue

        for rupture in ruptures:
            with filtruptures_mon:
                r_sites = filters.filter_sites_by_distance_to_rupture(
                    rupture, maximum_distance, s_sites)
                if r_sites is None:
                    continue
            yield SourceRuptureSites(src, rupture, r_sites)
    filtsources_mon.flush()
    genruptures_mon.flush()
    filtruptures_mon.flush()


def gen_ruptures_for_site(site, sources, maximum_distance, monitor):
    """
    Yield source, <ruptures close to site>

    :param site: a Site object
    :param sources: a sequence of sources
    :param monitor: a Monitor object
    """
    source_rupture_sites = gen_ruptures(
        sources, SiteCollection([site]), maximum_distance, monitor)
    for src, rows in itertools.groupby(
            source_rupture_sites, key=operator.attrgetter('source')):
        yield src, [row.rupture for row in rows]


def calc_gmfs(oqparam, sitecol, rupture=None, seed=None, realizations=None):
    """
    Build all the ground motion fields for the whole site collection in
    a single step.
    """
    max_dist = oqparam.maximum_distance
    correl_model = oqparam.correlation_model
    seed = oqparam.random_seed
    imts = map(from_string, sorted(oqparam.intensity_measure_and_types))
    gsim = get_gsim(oqparam)
    trunc_level = getattr(oqparam, 'truncation_level', None)
    n_gmfs = getattr(oqparam, 'number_of_ground_motion_fields', 1)
    rupture = get_rupture(oqparam)
    res = gmf.ground_motion_fields(
        rupture, sitecol, imts, gsim,
        trunc_level, realizations or n_gmfs, correl_model,
        filters.rupture_site_distance_filter(max_dist), seed)
    return {str(imt): matrix for imt, matrix in res.iteritems()}


def make_epsilons(oqparam, asset_count):
    """
    Build all the epsilons for the asset of a given taxonomy in
    a single step
    """
    num_samples = oqparam.number_of_ground_motion_fields
    seed = oqparam.master_seed
    correlation = getattr(oqparam, 'asset_correlation', 0)
    return scientific.make_epsilons(
        numpy.zeros(asset_count, num_samples),
        seed, correlation)


def run_scenario(oqparam):
    """
    Run a scenario damage or scenario risk computation
    """
    sitecol, assets_by_site = get_sitecol_assets(oqparam)
    gmfs_by_imt = calc_gmfs(oqparam, sitecol)
    risk_inputs = []
    for imt in gmfs_by_imt:
        for site, assets, gmvs in zip(
                sitecol, assets_by_site, gmfs_by_imt[imt]):
            risk_inputs.append(workflows.RiskInput(imt, assets, gmvs))

    risk_models = get_risk_models(oqparam)
    aggfractions = apply_reduce(calc_damage, (riskinputs, risk_models),
                                key=lambda ri: ri.imt,
                                weight=lambda ri: ri.weight)
    print aggfractions


def calc_damage(riskinputs, risk_models):
    aggfractions = {}  # taxonomy -> aggfractions
    for riskinput in riskinputs:
        for ri in riskinput.split_by_taxonomy():
            risk_model = risk_models[ri.imt, ri.taxonomy]
            fractions = risk_model.workflow(ri.get_hazard())
            aggfractions[ri.taxonomy] += sum(
                fraction * asset.number_of_units
                for fraction, asset in zip(fractions, ri.assets))
    return aggfractions
