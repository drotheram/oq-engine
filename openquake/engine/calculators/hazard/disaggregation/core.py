# -*- coding: utf-8 -*-
# Copyright (c) 2010-2014, GEM Foundation.
#
# OpenQuake is free software: you can redistribute it and/or modify it
# under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# OpenQuake is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with OpenQuake.  If not, see <http://www.gnu.org/licenses/>.

"""
Disaggregation calculator core functionality
"""

import sys
from collections import OrderedDict, namedtuple, defaultdict
import numpy

from openquake.hazardlib.calc import disagg
from openquake.hazardlib.imt import from_string
from openquake.hazardlib.geo.utils import get_longitudinal_extent
from openquake.hazardlib.geo.utils import get_spherical_bounding_box
from openquake.hazardlib.site import SiteCollection
from openquake.hazardlib.geo.geodetic import npoints_between

from openquake.engine import logs
from openquake.engine.db import models
from openquake.engine.utils import tasks
from openquake.engine.performance import EnginePerformanceMonitor, LightMonitor
from openquake.engine.calculators.hazard.classical.core import \
    ClassicalHazardCalculator


# a 6-uple containing float 4 arrays mags, dists, lons, lats,
# 1 int array trts and a list of dictionaries pnes
BinData = namedtuple('BinData', 'mags, dists, lons, lats, trts, pnes')


def dist_lon_lat_edges(dists, lons, lats, dist_bin_width, coord_bin_width):
    """
    Define bin edges for disaggregation histograms, from the bin data
    collected from the ruptures.

    :param dists:
        array of distances from the ruptures
    :param lons:
        array of longitudes from the ruptures
    :param lats:
        array of latitudes from the ruptures
    :param dist_bin_width:
        distance_bin_width from job.ini
    :param coord_bin_width:
        coordinate_bin_width from job.ini
    """
    dist_edges = dist_bin_width * numpy.arange(
        int(numpy.floor(min(dists) / dist_bin_width)),
        int(numpy.ceil(max(dists) / dist_bin_width) + 1))

    west, east, north, south = get_spherical_bounding_box(lons, lats)
    west = numpy.floor(west / coord_bin_width) * coord_bin_width
    east = numpy.ceil(east / coord_bin_width) * coord_bin_width
    lon_extent = get_longitudinal_extent(west, east)

    lon_edges, _, _ = npoints_between(
        west, 0, 0, east, 0, 0,
        numpy.round(lon_extent / coord_bin_width) + 1)

    lat_edges = coord_bin_width * numpy.arange(
        int(numpy.floor(south / coord_bin_width)),
        int(numpy.ceil(north / coord_bin_width) + 1))

    return dist_edges, lon_edges, lat_edges


def pmf_dict(matrix):
    """
    Return an OrderedDict of matrices with the key in the dictionary
    `openquake.hazardlib.calc.disagg.pmf_map`.

    :param matrix: an :class:`openquake.engine.db.models.
    """
    return OrderedDict((key, pmf_fn(matrix))
                       for key, pmf_fn in disagg.pmf_map.iteritems())


def _collect_bins_data(mon, trt_num, source_ruptures, site, curves,
                       gsims_by_rlz, imtls, poes, truncation_level,
                       n_epsilons):
    # returns a BinData instance
    sitecol = SiteCollection([site])
    mags = []
    dists = []
    lons = []
    lats = []
    trts = []
    pnes = []
    sitemesh = sitecol.mesh
    calc_dist = mon.copy('calc distances')
    make_ctxt = mon.copy('making contexts')
    disagg_poe = mon.copy('disaggregate_poe')

    for source, ruptures in source_ruptures:
        try:
            tect_reg = trt_num[source.tectonic_region_type]
            for rupture in ruptures:
                # extract rupture parameters of interest
                mags.append(rupture.mag)
                with calc_dist:
                    [jb_dist] = rupture.surface.get_joyner_boore_distance(
                        sitemesh)
                    dists.append(jb_dist)
                    [closest_point] = rupture.surface.get_closest_points(
                        sitemesh)
                lons.append(closest_point.longitude)
                lats.append(closest_point.latitude)
                trts.append(tect_reg)

                pne_dict = {}
                # a dictionary rlz.id, poe, imt_str -> prob_no_exceed
                for rlz, gsims in gsims_by_rlz.items():
                    gsim = gsims[source.tectonic_region_type]
                    with make_ctxt:
                        sctx, rctx, dctx = gsim.make_contexts(sitecol, rupture)
                    for imt_str, imls in imtls.iteritems():
                        imt = from_string(imt_str)
                        imls = numpy.array(imls[::-1])
                        curve_poes = curves[rlz.id, imt_str].poes[::-1]

                        for poe in poes:
                            iml = numpy.interp(poe, curve_poes, imls)
                            # compute probability of exceeding iml given
                            # the current rupture and epsilon level, that is
                            # ``P(IMT >= iml | rup, epsilon_bin)``
                            # for each of the epsilon bins
                            with disagg_poe:
                                [poes_given_rup_eps] = gsim.disaggregate_poe(
                                    sctx, rctx, dctx, imt, iml,
                                    truncation_level, n_epsilons)
                            pne = rupture.get_probability_no_exceedance(
                                poes_given_rup_eps)
                            pne_dict[rlz.id, poe, imt_str] = (pne, iml)

                pnes.append(pne_dict)
        except Exception as err:
            etype, err, tb = sys.exc_info()
            msg = 'An error occurred with source id=%s. Error: %s'
            msg %= (source.source_id, err.message)
            raise etype, msg, tb

    calc_dist.flush()
    make_ctxt.flush()
    disagg_poe.flush()

    return BinData(numpy.array(mags, float),
                   numpy.array(dists, float),
                   numpy.array(lons, float),
                   numpy.array(lats, float),
                   numpy.array(trts, int),
                   pnes)


_DISAGG_RES_NAME_FMT = 'disagg(%(poe)s)-rlz-%(rlz)s-%(imt)s-%(wkt)s'


def save_disagg_result(job_id, site_id, bin_edges, trt_names, pmf_dict,
                       rlz_id, investigation_time, imt_str, iml, poe):
    """
    Save a computed disaggregation matrix to `hzrdr.disagg_result` (see
    :class:`~openquake.engine.db.models.DisaggResult`).

    :param int job_id:
        id of the current job.
    :param int site_id:
        id of the current site
    :param bin_edges:
        The 5-uple mag, dist, lon, lat, eps
    :param trt_names:
        The list of Tectonic Region Types
    :param pmf_dict:
        A dictionary key -> probability array, with key in the pmf_map
    :param rlz:
        :class:`openquake.engine.db.models.LtRealization` to which these
        results belong.
    :param float investigation_time:
        Investigation time (years) for the calculation.
    :param imt_str:
        Intensity measure type (PGA, SA, etc.)
    :param float iml:
        Intensity measure level interpolated (using ``poe``) from the hazard
        curve at the ``site``.
    :param float poe:
        Disaggregation probability of exceedance value for this result.
    """
    job = models.OqJob.objects.get(id=job_id)

    site_wkt = models.HazardSite.objects.get(pk=site_id).location.wkt

    disp_name = _DISAGG_RES_NAME_FMT % dict(
        poe=poe, rlz=rlz_id, imt=imt_str, wkt=site_wkt)

    output = models.Output.objects.create_output(
        job, disp_name, 'disagg_matrix')

    imt, sa_period, sa_damping = from_string(imt_str)
    mag, dist, lon, lat, eps = bin_edges
    models.DisaggResult.objects.create(
        output=output,
        lt_realization_id=rlz_id,
        investigation_time=investigation_time,
        imt=imt,
        sa_period=sa_period,
        sa_damping=sa_damping,
        iml=iml,
        poe=poe,
        mag_bin_edges=mag,
        dist_bin_edges=dist,
        lon_bin_edges=lon,
        lat_bin_edges=lat,
        eps_bin_edges=eps,
        trts=trt_names,
        location=site_wkt,
        matrix=pmf_dict,
    )


@tasks.oqtask
def compute_disagg(job_id, sources, lt_model, gsims_by_rlz,
                   trt_num, curves_dict, bin_edges):
    """
    :param int job_id:
        ID of the currently running :class:`openquake.engine.db.models.OqJob`
    :param list sources:
        list of hazardlib source objects
    :param lt_model:
        an instance of :class:`openquake.engine.db.models.LtSourceModel`
    :param dict gsims_by_rlz:
        a dictionary of gsim dictionaries, one for each realization
    :param dict trt_num:
        a dictionary Tectonic Region Type -> incremental number
    :param curves_dict:
        a dictionary with the hazard curves for all sites, realizations and IMTs
    :returns:
        a dictionary of pmf dictionaries, which composite key
        (site.id, rlz.id, poe, imt, probs.iml, trt_names).
    """
    mon = LightMonitor('disagg', job_id, compute_disagg)
    hc = models.OqJob.objects.get(id=job_id).hazard_calculation
    trt_names = tuple(lt_model.tectonic_region_types)
    result = {}  # site.id, rlz.id, poe, imt, iml, trt_names -> pmf

    for site in hc.site_collection:
        # edges as wanted by disagg._arrange_data_in_bins
        edges = bin_edges[lt_model.id, site.id] + (trt_names,)

        # generate source, rupture, sites once per site
        source_ruptures = list(hc.gen_ruptures_for_site(site, sources, mon))
        if not source_ruptures:
            continue
        logs.LOG.info('Collecting bins from %d ruptures close to %s',
                      sum(len(rupts) for src, rupts in source_ruptures),
                      site.location)

        with EnginePerformanceMonitor(
                'collecting bins', job_id, compute_disagg):
            bdata = _collect_bins_data(
                mon, trt_num, source_ruptures, site, curves_dict[site.id],
                gsims_by_rlz, hc.intensity_measure_types_and_levels,
                hc.poes_disagg, hc.truncation_level,
                hc.num_epsilon_bins)

        if not bdata.pnes:  # no contributions for this site
            continue

        for poe in hc.poes_disagg:
            for imt in hc.intensity_measure_types_and_levels:
                for rlz in gsims_by_rlz:

                    # extract the probabilities of non-exceedance for the
                    # given realization, disaggregation PoE, and IMT
                    iml_pne_pairs = [pne[rlz.id, poe, imt]
                                     for pne in bdata.pnes]
                    iml = iml_pne_pairs[0][0]
                    probs = numpy.array([p for (i, p) in iml_pne_pairs], float)
                    # bins in a format handy for hazardlib
                    bins = [bdata.mags, bdata.dists, bdata.lons, bdata.lats,
                            bdata.trts, None, probs]

                    # call disagg._arrange_data_in_bins and populate the result
                    with EnginePerformanceMonitor(
                            'arranging bins', job_id, compute_disagg):
                        key = site.id, rlz.id, poe, imt, probs.iml, trt_names
                        matrix = disagg._arrange_data_in_bins(bins, edges)
                        result[key] = pmf_dict(matrix)

    return result


class DisaggHazardCalculator(ClassicalHazardCalculator):
    """
    A calculator which performs disaggregation calculations in a distributed /
    parallelized fashion.

    See :func:`openquake.hazardlib.calc.disagg.disaggregation` for more
    details about the nature of this type of calculation.
    """
    def get_curves(self, site):
        """
        Get all the relevant hazard curves for the given site.
        Returns a dictionary {(rlz_id, imt) -> curve}.
        """
        dic = {}
        wkt = site.location.wkt2d
        for rlz in self._get_realizations():
            for imt_str in self.hc.intensity_measure_types_and_levels:
                imt = from_string(imt_str)
                [curve] = models.HazardCurveData.objects.filter(
                    location=wkt,
                    hazard_curve__lt_realization=rlz,
                    hazard_curve__imt=imt[0],
                    hazard_curve__sa_period=imt[1],
                    hazard_curve__sa_damping=imt[2])
                if all(x == 0.0 for x in curve.poes):
                    logs.LOG.warn(
                        '* hazard curve %d contains all zero '
                        'probabilities; skipping SRID=4326;%s, rlz=%d, IMT=%s',
                        curve.id, wkt, rlz.id, imt_str)
                    continue
                dic[rlz.id, imt_str] = curve
        return dic

    @EnginePerformanceMonitor.monitor
    def full_disaggregation(self):
        """
        Run the disaggregation phase after hazard curve finalization.
        """
        super(DisaggHazardCalculator, self).post_execute()
        hc = self.hc
        tl = self.hc.truncation_level
        mag_bin_width = self.hc.mag_bin_width
        eps_bins = numpy.linspace(-tl, tl, self.hc.num_epsilon_bins + 1)

        arglist = []
        bin_edges = {}
        curves_dict = dict((site.id, self.get_curves(site))
                           for site in self.hc.site_collection)

        for job_id, srcs, lt_model, gsims_by_rlz, task_no in \
                self.task_arg_gen():
            for site in self.hc.site_collection:
                curves = curves_dict[site.id]
                if not curves:
                    continue  # skip zero-valued hazard curves
                bb = self.bb_dict[lt_model.id, site.id]
                if not bb:
                    logs.LOG.info(
                        'location %s was too far, skipping disaggregation',
                        site.location)
                    continue

                dist_edges, lon_edges, lat_edges = dist_lon_lat_edges(
                    [bb.min_dist, bb.max_dist],
                    [bb.west, bb.east],
                    [bb.south, bb.north],
                    hc.distance_bin_width,
                    hc.coordinate_bin_width)

                trt_num = dict((trt, i) for i, trt in enumerate(
                               lt_model.tectonic_region_types))
                infos = list(models.LtModelInfo.objects.filter(
                             lt_model=lt_model))

                max_mag = max(i.max_mag for i in infos)
                min_mag = min(i.min_mag for i in infos)
                mag_edges = mag_bin_width * numpy.arange(
                    int(numpy.floor(min_mag / mag_bin_width)),
                    int(numpy.ceil(max_mag / mag_bin_width) + 1))

                logs.LOG.info('%d mag bins from %s to %s', len(mag_edges) - 1,
                              min_mag, max_mag)
                logs.LOG.info('%d dist bins from %s to %s', len(dist_edges) - 1,
                              min(dist_edges), max(dist_edges))
                logs.LOG.info('%d lon bins from %s to %s', len(lon_edges) - 1,
                              bb.west, bb.east)
                logs.LOG.info('%d lat bins from %s to %s', len(lon_edges) - 1,
                              bb.south, bb.north)

                bin_edges[lt_model.id, site.id] = (
                    mag_edges, dist_edges, lon_edges, lat_edges, eps_edges)

            arglist.append((self.job.id, srcs, lt_model, gsims_by_rlz,
                            trt_num, curves_dict, bin_edges))

        res = tasks.map_reduce(compute_disagg, arglist, self.agg_result, {})
        self.save_results(res)  # dictionary key -> pmf_dict

    @EnginePerformanceMonitor.monitor
    def save_disagg_results(self, results):
        """
        The number of results to save is
        #sites * #rlzs * #disagg_poes * #IMTs
        """
        for key, pmf_dict in results.iteritems():
            site_id, rlz_id, poe, imt, iml, trt_names = key
            lt_model = models.LtRealization.objects.get(pk=rlz_id).lt_model
            edges = bin_edges[lt_model.id, site_id]
            save_disagg_result(job_id, site_id, edges, trt_names, pmf_dict,
                               rlz_id, hc.investigation_time, imt, iml, poe)

    post_execute = full_disaggregation

    def agg_result(self, acc, result):
        """
        Collect the results coming from compute_disagg into self.results,
        a dictionary with key site.id, rlz.id, poe, imt, iml, trt_names
        and pmf dictionaries as values.
        """
        new_acc = {}
        for key, pmf_dict in result.iteritems():
            new_acc[key] = {}
            a = acc.get(key, {})
            for pmf_key, pmf_vals in pmf_dict.iteritems():
                new_acc[key][pmf_key] = 1. - (1. - a.get(pmf_key, 0)) * (
                    1. - pmf_vals)
        self.log_percent()
        return acc
