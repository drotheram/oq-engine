# -*- coding: utf-8 -*-
# vim: tabstop=4 shiftwidth=4 softtabstop=4
#
# Copyright (C) 2015-2020 GEM Foundation
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
import unittest
import unittest.mock as mock
import numpy
from openquake.baselib import parallel, general
from openquake.hazardlib import lt
from openquake.calculators.views import view, rst_table
from openquake.calculators.export import export
from openquake.calculators.extract import extract
from openquake.calculators.getters import PmapGetter
from openquake.calculators.tests import CalculatorTestCase, NOT_DARWIN
from openquake.qa_tests_data.classical import (
    case_1, case_2, case_3, case_4, case_5, case_6, case_7, case_8, case_9,
    case_10, case_11, case_12, case_13, case_14, case_15, case_16, case_17,
    case_18, case_19, case_20, case_21, case_22, case_23, case_24, case_25,
    case_26, case_27, case_28, case_29, case_30, case_31, case_32, case_33,
    case_34, case_35, case_36, case_37, case_38, case_39, case_40, case_41,
    case_42, case_43, case_44, case_45, case_46, case_47, case_48)

aac = numpy.testing.assert_allclose


def check_disagg_by_src(dstore):
    """
    Make sure that by composing disagg_by_src one gets the hazard curves
    """
    mean = dstore.sel('hcurves-stats', stat='mean')[:, 0]  # N, M, L
    dbs = dstore.sel('disagg_by_src')  # N, R, M, L, Ns
    poes = general.pprod(dbs, axis=4)  # N, R, M, L
    weights = dstore['weights'][:]
    mean2 = numpy.einsum('sr...,r->s...', poes, weights)  # N, M, L
    aac(mean, mean2, atol=1E-6)


class ClassicalTestCase(CalculatorTestCase):

    def assert_curves_ok(self, expected, test_dir, delta=None, **kw):
        kind = kw.pop('kind', '')
        self.run_calc(test_dir, 'job.ini', **kw)
        ds = self.calc.datastore
        got = (export(('hcurves/' + kind, 'csv'), ds) +
               export(('hmaps/' + kind, 'csv'), ds) +
               export(('uhs/' + kind, 'csv'), ds))
        self.assertEqual(len(expected), len(got), str(got))
        for fname, actual in zip(expected, got):
            self.assertEqualFiles('expected/%s' % fname, actual,
                                  delta=delta)
        return got

    def test_case_1(self):
        self.assert_curves_ok(
            ['hazard_curve-PGA.csv', 'hazard_curve-SA(0.1).csv'],
            case_1.__file__)

        if parallel.oq_distribute() != 'no':
            info = view('job_info', self.calc.datastore)
            self.assertIn('task', info)
            self.assertIn('sent', info)
            self.assertIn('received', info)

            slow = view('task:classical_split_filter:-1', self.calc.datastore)
            self.assertIn('taskno', slow)
            self.assertIn('duration', slow)
            self.assertIn('sources', slow)

        # there is a single source
        self.assertEqual(len(self.calc.datastore['source_info']), 1)

        # check npz export
        export(('hcurves', 'npz'), self.calc.datastore)

        # check extraction
        sitecol = extract(self.calc.datastore, 'sitecol')
        self.assertEqual(len(sitecol.array), 1)

        # check minimum_magnitude discards the source
        with self.assertRaises(RuntimeError) as ctx:
            self.run_calc(case_1.__file__, 'job.ini', minimum_magnitude='4.5')
        self.assertEqual(str(ctx.exception), 'All sources were discarded!?')

    def test_wrong_smlt(self):
        with self.assertRaises(lt.LogicTreeError):
            self.run_calc(case_1.__file__, 'job_wrong.ini')

    def test_sa_period_too_big(self):
        imtls = '{"SA(4.1)": [0.1, 0.4, 0.6]}'
        with self.assertRaises(ValueError) as ctx:
            self.run_calc(
                case_1.__file__, 'job.ini',
                intensity_measure_types_and_levels=imtls)
        self.assertEqual(
            'SA(4.1) is out of the period range defined for [SadighEtAl1997]',
            str(ctx.exception))

    def test_case_2(self):
        self.run_calc(case_2.__file__, 'job.ini')

        # check view_pmap for a single realization
        got = view('pmap:grp-00', self.calc.datastore)
        self.assertEqual(got, '<ProbabilityMap 1, 4, 1>')

        # check view inputs
        lines = view('inputs', self.calc.datastore).splitlines()
        self.assertEqual(len(lines), 9)

        [fname] = export(('hcurves', 'csv'), self.calc.datastore)
        self.assertEqualFiles('expected/hcurve.csv', fname)

        # check disagg_by_src for a single realization
        check_disagg_by_src(self.calc.datastore)

    def test_case_3(self):
        self.assert_curves_ok(
            ['hazard_curve-smltp_b1-gsimltp_b1.csv'],
            case_3.__file__)

    def test_case_4(self):
        self.assert_curves_ok(
            ['hazard_curve-smltp_b1-gsimltp_b1.csv'],
            case_4.__file__)

    def test_case_5(self):
        self.assert_curves_ok(
            ['hazard_curve-smltp_b1-gsimltp_b1.csv'],
            case_5.__file__)

    def test_case_6(self):
        self.assert_curves_ok(
            ['hazard_curve-smltp_b1-gsimltp_b1.csv'],
            case_6.__file__)

    def test_case_7(self):
        # this is a case with duplicated sources
        self.assert_curves_ok(
            ['hazard_curve-mean.csv',
             'hazard_curve-smltp_b1-gsimltp_b1.csv',
             'hazard_curve-smltp_b2-gsimltp_b1.csv'],
            case_7.__file__)

        # exercising extract/mean_std_curves
        # extract(self.calc.datastore, 'mean_std_curves')

        # exercise the warning for no output when mean_hazard_curves='false'
        self.run_calc(
            case_7.__file__, 'job.ini', mean_hazard_curves='false',
            calculation_mode='preclassical',  poes='0.1')

    def test_case_8(self):
        self.assert_curves_ok(
            ['hazard_curve-smltp_b1_b2-gsimltp_b1.csv',
             'hazard_curve-smltp_b1_b3-gsimltp_b1.csv',
             'hazard_curve-smltp_b1_b4-gsimltp_b1.csv'],
            case_8.__file__)

    def test_case_9(self):
        self.assert_curves_ok(
            ['hazard_curve-smltp_b1_b2-gsimltp_b1.csv',
             'hazard_curve-smltp_b1_b3-gsimltp_b1.csv'],
            case_9.__file__)

    def test_case_10(self):
        self.assert_curves_ok(
            ['hazard_curve-smltp_b1_b2-gsimltp_b1.csv',
             'hazard_curve-smltp_b1_b3-gsimltp_b1.csv'],
            case_10.__file__)

    def test_case_11(self):
        self.assert_curves_ok(
            ['hazard_curve-mean.csv',
             'hazard_curve-smltp_b1_b2-gsimltp_b1.csv',
             'hazard_curve-smltp_b1_b3-gsimltp_b1.csv',
             'hazard_curve-smltp_b1_b4-gsimltp_b1.csv',
             'quantile_curve-0.1.csv',
             'quantile_curve-0.9.csv'],
            case_11.__file__)

        # checking PmapGetter.get_pcurve
        pgetter = PmapGetter(self.calc.datastore, self.calc.weights)
        poes = pgetter.get_hcurves(pgetter.init())[0]
        mean = self.calc.datastore.sel('hcurves-stats', stat='mean', sid=0)
        mean2 = poes.T @ numpy.array([w['weight'] for w in self.calc.weights])
        aac(mean2.flat, mean.flat)
        check_disagg_by_src(self.calc.datastore)

    def test_case_12(self):
        # test Modified GMPE
        self.assert_curves_ok(
            ['hazard_curve-smltp_b1-gsimltp_b1_b2.csv'],
            case_12.__file__)

    def test_case_13(self):
        self.assert_curves_ok(
            ['hazard_curve-mean_PGA.csv', 'hazard_curve-mean_SA(0.2).csv',
             'hazard_map-mean.csv'], case_13.__file__)

        # test recomputing the hazard maps
        self.run_calc(
            case_13.__file__, 'job.ini', exports='csv',
            hazard_calculation_id=str(self.calc.datastore.calc_id),
            gsim_logic_tree_file='', source_model_logic_tree_file='')
        [fname] = export(('hmaps', 'csv'), self.calc.datastore)
        self.assertEqualFiles('expected/hazard_map-mean.csv', fname,
                              delta=1E-5)

        # test extract/hcurves/rlz-0, used by the npz exports
        haz = vars(extract(self.calc.datastore, 'hcurves'))
        self.assertEqual(sorted(haz), ['_extra', 'all', 'investigation_time'])
        self.assertEqual(
            haz['all'].dtype.names, ('lon', 'lat', 'depth', 'mean'))
        array = haz['all']['mean']
        self.assertEqual(array.dtype.names, ('PGA', 'SA(0.2)'))
        self.assertEqual(array['PGA'].dtype.names,
                         ('0.005', '0.007', '0.0098', '0.0137', '0.0192',
                          '0.0269', '0.0376', '0.0527', '0.0738', '0.103',
                          '0.145', '0.203', '0.284'))

        # test disagg_by_src in a complex case with duplicated sources
        check_disagg_by_src(self.calc.datastore)

    def test_case_14(self):
        # test classical with 2 gsims and 1 sample
        self.assert_curves_ok(['hazard_curve-rlz-000_PGA.csv'],
                              case_14.__file__)

        # test sampling use the right number of gsims by looking at
        # the poes datasets which have shape (N, L, G)
        G = 1  # and not 2
        self.calc.datastore['poes/grp-00'].array.shape[-1] == G

        # test preclassical and OQ_SAMPLE_SOURCES
        with mock.patch.dict(os.environ, OQ_SAMPLE_SOURCES='1'):
            self.run_calc(
                case_14.__file__, 'job.ini', calculation_mode='preclassical')

    def test_case_15(self):
        # this is a case with both splittable and unsplittable sources
        self.assert_curves_ok('''\
hazard_curve-max-PGA.csv,
hazard_curve-max-SA(0.1).csv
hazard_curve-mean-PGA.csv
hazard_curve-mean-SA(0.1).csv
hazard_curve-std-PGA.csv
hazard_curve-std-SA(0.1).csv
hazard_uhs-max.csv
hazard_uhs-mean.csv
hazard_uhs-std.csv
'''.split(), case_15.__file__, delta=1E-6)

        # test UHS XML export
        fnames = [f for f in export(('uhs', 'xml'), self.calc.datastore)
                  if 'mean' in f]
        self.assertEqualFiles('expected/hazard_uhs-mean-0.01.xml', fnames[0])
        self.assertEqualFiles('expected/hazard_uhs-mean-0.1.xml', fnames[1])
        self.assertEqualFiles('expected/hazard_uhs-mean-0.2.xml', fnames[2])

        # npz exports
        [fname] = export(('hmaps', 'npz'), self.calc.datastore)
        arr = numpy.load(fname)['all']
        self.assertEqual(arr['mean'].dtype.names, ('PGA', 'SA(0.1)'))
        [fname] = export(('uhs', 'npz'), self.calc.datastore)
        arr = numpy.load(fname)['all']
        self.assertEqual(arr['mean'].dtype.names, ('0.01', '0.1', '0.2'))

        # check deserialization of source_model_lt
        smlt = self.calc.datastore['full_lt/source_model_lt']
        exp = str(list(smlt))
        self.assertEqual('''[<Realization #0 source_model_1.xml, path=SM1, weight=0.5>, <Realization #1 source_model_2.xml, path=SM2_a3pt2b0pt8, weight=0.25>, <Realization #2 source_model_2.xml, path=SM2_a3b1, weight=0.25>]''', exp)

    def test_case_16(self):   # sampling
        self.assert_curves_ok(
            ['hazard_curve-mean.csv',
             'quantile_curve-0.1.csv',
             'quantile_curve-0.9.csv'],
            case_16.__file__)

        # test that the single realization export fails because
        # individual_curves was false
        with self.assertRaises(KeyError) as ctx:
            export(('hcurves/rlz-3', 'csv'), self.calc.datastore)
        self.assertIn("No 'hcurves-rlzs' found", str(ctx.exception))

    def test_case_17(self):  # oversampling
        # this is a test with 4 sources A and B with the same ID
        # sources A's are false duplicates, while the B's are true duplicates
        self.assert_curves_ok(
            ['hazard_curve-smltp_b1-gsimltp_b1-ltr_0.csv',
             'hazard_curve-smltp_b2-gsimltp_b1-ltr_1.csv',
             'hazard_curve-smltp_b2-gsimltp_b1-ltr_2.csv',
             'hazard_curve-smltp_b2-gsimltp_b1-ltr_3.csv',
             'hazard_curve-smltp_b2-gsimltp_b1-ltr_4.csv'],
            case_17.__file__)
        arr = self.calc.datastore['source_info'][:]
        mul = dict(arr[['source_id', 'multiplicity']])
        self.assertEqual(mul['A'], 2)  # different, multiplicity > 1
        self.assertEqual(mul['B'], 1)  # duplicates

    def test_case_18(self):  # GMPEtable
        self.assert_curves_ok(
            ['hazard_curve-mean_PGA.csv',
             'hazard_curve-mean_SA(0.2).csv',
             'hazard_curve-mean_SA(1.0).csv',
             'hazard_map-mean.csv',
             'hazard_uhs-mean.csv'],
            case_18.__file__, kind='stats', delta=1E-7)
        [fname] = export(('realizations', 'csv'), self.calc.datastore)
        self.assertEqualFiles('expected/realizations.csv', fname)

        if os.environ.get('TRAVIS'):
            raise unittest.SkipTest('Randomly broken on Travis')

        self.calc.datastore.close()
        self.calc.datastore.open('r')

        # check exporting a single realization in CSV and XML
        [fname] = export(('uhs/rlz-001', 'csv'),  self.calc.datastore)
        self.assertEqualFiles('expected/uhs-rlz-1.csv', fname)
        [fname] = export(('uhs/rlz-001', 'xml'),  self.calc.datastore)
        self.assertEqualFiles('expected/uhs-rlz-1.xml', fname)

        # extracting hmaps
        hmaps = extract(self.calc.datastore, 'hmaps')['all']['mean']
        self.assertEqual(hmaps.dtype.names, ('PGA', 'SA(0.2)', 'SA(1.0)'))

    def test_case_19(self):
        # test for AvgGMPE and pointsource_distance
        self.assert_curves_ok([
            'hazard_curve-mean_PGA.csv',
            'hazard_curve-mean_SA(0.1).csv',
            'hazard_curve-mean_SA(0.15).csv',
        ], case_19.__file__, delta=1E-5)

    def test_case_20(self):
        # Source geometry enumeration, apply_to_sources
        self.assert_curves_ok([
            'hazard_curve-mean-PGA.csv',
            'hazard_curve-smltp_sm1_sg1_cog1_char_complex-gsimltp_Sad1997.csv',
            'hazard_curve-smltp_sm1_sg1_cog1_char_plane-gsimltp_Sad1997.csv',
            'hazard_curve-smltp_sm1_sg1_cog1_char_simple-gsimltp_Sad1997.csv',
            'hazard_curve-smltp_sm1_sg1_cog2_char_complex-gsimltp_Sad1997.csv',
            'hazard_curve-smltp_sm1_sg1_cog2_char_plane-gsimltp_Sad1997.csv',
            'hazard_curve-smltp_sm1_sg1_cog2_char_simple-gsimltp_Sad1997.csv',
            'hazard_curve-smltp_sm1_sg2_cog1_char_complex-gsimltp_Sad1997.csv',
            'hazard_curve-smltp_sm1_sg2_cog1_char_plane-gsimltp_Sad1997.csv',
            'hazard_curve-smltp_sm1_sg2_cog1_char_simple-gsimltp_Sad1997.csv',
            'hazard_curve-smltp_sm1_sg2_cog2_char_complex-gsimltp_Sad1997.csv',
            'hazard_curve-smltp_sm1_sg2_cog2_char_plane-gsimltp_Sad1997.csv',
            'hazard_curve-smltp_sm1_sg2_cog2_char_simple-gsimltp_Sad1997.csv'],
            case_20.__file__, delta=1E-7)
        # there are 3 sources x 12 sm_rlzs
        [sg] = self.calc.csm.src_groups  # 1 source group with 7 sources
        self.assertEqual(len(sg), 7)
        tbl = []
        for src in sg:
            tbl.append((src.source_id, src.checksum) + src.grp_ids)
        tbl.sort()
        '''
        self.assertEqual(tbl,
                         [['CHAR1', 1020111046, 2, 5, 8, 11],
                          ['CHAR1', 1117683992, 0, 3, 6, 9],
                          ['CHAR1', 1442321585, 1, 4, 7, 10],
                          ['COMFLT1', 2221824602, 3, 4, 5, 9, 10, 11],
                          ['COMFLT1', 3381942518, 0, 1, 2, 6, 7, 8],
                          ['SFLT1', 4233779789, 6, 7, 8, 9, 10, 11],
                          ['SFLT1', 4256912415, 0, 1, 2, 3, 4, 5]])
        '''
        dupl = sum(len(src.grp_ids) - 1 for src in sg)
        self.assertEqual(dupl, 29)  # there are 29 duplicated sources

        # another way to look at the duplicated sources; protects against
        # future refactorings breaking the pandas readability of source_info
        df = self.calc.datastore.read_df('source_info', 'source_id')
        dic = dict(df['multiplicity'])
        self.assertEqual(dic, {'CHAR1': 3, 'COMFLT1': 2, 'SFLT1': 2})

        # check pandas readability of hcurves-rlzs and hcurves-stats
        df = self.calc.datastore.read_df('hcurves-rlzs', 'lvl')
        self.assertEqual(list(df.columns),
                         ['site_id', 'rlz_id', 'imt', 'value'])
        df = self.calc.datastore.read_df('hcurves-stats', 'lvl')
        self.assertEqual(list(df.columns),
                         ['site_id', 'stat', 'imt', 'value'])

    def test_case_21(self):
        # Simple fault dip and MFD enumeration
        self.assert_curves_ok([
            'hazard_curve-smltp_b1_mfd1_high_dip_dip30-gsimltp_Sad1997.csv',
            'hazard_curve-smltp_b1_mfd1_high_dip_dip45-gsimltp_Sad1997.csv',
            'hazard_curve-smltp_b1_mfd1_high_dip_dip60-gsimltp_Sad1997.csv',
            'hazard_curve-smltp_b1_mfd1_low_dip_dip30-gsimltp_Sad1997.csv',
            'hazard_curve-smltp_b1_mfd1_low_dip_dip45-gsimltp_Sad1997.csv',
            'hazard_curve-smltp_b1_mfd1_low_dip_dip60-gsimltp_Sad1997.csv',
            'hazard_curve-smltp_b1_mfd1_mid_dip_dip30-gsimltp_Sad1997.csv',
            'hazard_curve-smltp_b1_mfd1_mid_dip_dip45-gsimltp_Sad1997.csv',
            'hazard_curve-smltp_b1_mfd1_mid_dip_dip60-gsimltp_Sad1997.csv',
            'hazard_curve-smltp_b1_mfd2_high_dip_dip30-gsimltp_Sad1997.csv',
            'hazard_curve-smltp_b1_mfd2_high_dip_dip45-gsimltp_Sad1997.csv',
            'hazard_curve-smltp_b1_mfd2_high_dip_dip60-gsimltp_Sad1997.csv',
            'hazard_curve-smltp_b1_mfd2_low_dip_dip30-gsimltp_Sad1997.csv',
            'hazard_curve-smltp_b1_mfd2_low_dip_dip45-gsimltp_Sad1997.csv',
            'hazard_curve-smltp_b1_mfd2_low_dip_dip60-gsimltp_Sad1997.csv',
            'hazard_curve-smltp_b1_mfd2_mid_dip_dip30-gsimltp_Sad1997.csv',
            'hazard_curve-smltp_b1_mfd2_mid_dip_dip45-gsimltp_Sad1997.csv',
            'hazard_curve-smltp_b1_mfd2_mid_dip_dip60-gsimltp_Sad1997.csv',
            'hazard_curve-smltp_b1_mfd3_high_dip_dip30-gsimltp_Sad1997.csv',
            'hazard_curve-smltp_b1_mfd3_high_dip_dip45-gsimltp_Sad1997.csv',
            'hazard_curve-smltp_b1_mfd3_high_dip_dip60-gsimltp_Sad1997.csv',
            'hazard_curve-smltp_b1_mfd3_low_dip_dip30-gsimltp_Sad1997.csv',
            'hazard_curve-smltp_b1_mfd3_low_dip_dip45-gsimltp_Sad1997.csv',
            'hazard_curve-smltp_b1_mfd3_low_dip_dip60-gsimltp_Sad1997.csv',
            'hazard_curve-smltp_b1_mfd3_mid_dip_dip30-gsimltp_Sad1997.csv',
            'hazard_curve-smltp_b1_mfd3_mid_dip_dip45-gsimltp_Sad1997.csv',
            'hazard_curve-smltp_b1_mfd3_mid_dip_dip60-gsimltp_Sad1997.csv'],
            case_21.__file__, delta=1E-7)

    def test_case_22(self):  # crossing date line calculation for Alaska
        # this also tests the splitting of the source model in two files
        self.assert_curves_ok([
            '/hazard_curve-mean-PGA.csv', 'hazard_curve-mean-SA(0.1)',
            'hazard_curve-mean-SA(0.2).csv', 'hazard_curve-mean-SA(0.5).csv',
            'hazard_curve-mean-SA(1.0).csv', 'hazard_curve-mean-SA(2.0).csv',
        ], case_22.__file__, delta=1E-6)

    def test_case_23(self):  # filtering away on TRT
        self.assert_curves_ok(['hazard_curve.csv'], case_23.__file__)
        checksum = self.calc.datastore['/'].attrs['checksum32']
        self.assertEqual(checksum, 3211843635)

    def test_case_24(self):  # UHS
        # this is a case with rjb and an hypocenter distribution
        self.assert_curves_ok([
            'hazard_curve-PGA.csv', 'hazard_curve-PGV.csv',
            'hazard_curve-SA(0.025).csv', 'hazard_curve-SA(0.05).csv',
            'hazard_curve-SA(0.1).csv', 'hazard_curve-SA(0.2).csv',
            'hazard_curve-SA(0.5).csv', 'hazard_curve-SA(1.0).csv',
            'hazard_curve-SA(2.0).csv', 'hazard_uhs.csv'], case_24.__file__)
        # test that the number of ruptures is at max 1/3 of the the total
        # due to the collapsing of the hypocenters (rjb is depth-independent)
        self.assertEqual(len(self.calc.datastore['rup/rrup_']), 174)
        self.assertEqual(self.calc.totrups, 780)

    def test_case_25(self):  # negative depths
        self.assert_curves_ok(['hazard_curve-smltp_b1-gsimltp_b1.csv'],
                              case_25.__file__)

    def test_case_26(self):  # split YoungsCoppersmith1985MFD
        self.assert_curves_ok(['hazard_curve-rlz-000.csv'], case_26.__file__)

    def test_case_27(self):  # Nankai mutex model
        self.assert_curves_ok(['hazard_curve.csv'], case_27.__file__)
        # make sure probs_occur are stored as expected
        probs_occur = self.calc.datastore['rup/probs_occur'][:]
        tot_probs_occur = sum(len(po) for po in probs_occur)
        self.assertEqual(tot_probs_occur, 28)  # 14 nonparam rups x 2
        npo = self.calc.csm.get_num_probs_occur()  # 2 probs_occur per rupture
        self.assertEqual(npo, 2)
        num_point_ruptures = sum(1 for po in probs_occur if len(po) == 0)
        self.assertEqual(num_point_ruptures, 26)

        # make sure there is an error when trying to disaggregate
        with self.assertRaises(NotImplementedError):
            hc_id = str(self.calc.datastore.calc_id)
            self.run_calc(case_27.__file__, 'job.ini',
                          hazard_calculation_id=hc_id,
                          calculation_mode='disaggregation',
                          truncation_level="3",
                          poes_disagg="0.02",
                          mag_bin_width="0.1",
                          distance_bin_width="10.0",
                          coordinate_bin_width="1.0",
                          num_epsilon_bins="6")

    def test_case_28(self):  # North Africa
        # MultiPointSource with modify MFD logic tree
        self.assert_curves_ok([
            'hazard_curve-mean-PGA.csv', 'hazard_curve-mean-SA(0.05).csv',
            'hazard_curve-mean-SA(0.1).csv', 'hazard_curve-mean-SA(0.2).csv',
            'hazard_curve-mean-SA(0.5)', 'hazard_curve-mean-SA(1.0).csv',
            'hazard_curve-mean-SA(2.0).csv'], case_28.__file__, delta=1E-6)

    def test_case_29(self):  # non parametric source
        # check the high IMLs are zeros: this is a test for
        # NonParametricProbabilisticRupture.get_probability_no_exceedance
        self.assert_curves_ok(['hazard_curve-PGA.csv'], case_29.__file__)

    def test_case_30(self):
        # point on the international data line
        # this is also a test with IMT-dependent weights
        if NOT_DARWIN:  # broken on macOS
            self.assert_curves_ok(['hazard_curve-PGA.csv',
                                   'hazard_curve-SA(1.0).csv'],
                                  case_30.__file__)
            # check rupdata
            nruptures = []
            for par, rupdata in sorted(self.calc.datastore['rup'].items()):
                nruptures.append((par, len(rupdata)))
            self.assertEqual(
                nruptures,
                [('clat_', 3202), ('clon_', 3202), ('dip', 3202),
                 ('grp_id', 3202), ('hypo_depth', 3202), ('mag', 3202),
                 ('occurrence_rate', 3202), ('probs_occur', 3202),
                 ('rake', 3202), ('rjb_', 3202), ('rrup_', 3202),
                 ('rx_', 3202), ('weight', 3202), ('ztor', 3202)])

    def test_case_30_sampling(self):
        # IMT-dependent weights with sampling by cheating
        self.assert_curves_ok(
            ['hcurve-PGA.csv', 'hcurve-SA(1.0).csv'],
            case_30.__file__, number_of_logic_tree_samples='10')

    def test_case_31(self):
        # source specific logic tree
        self.assert_curves_ok(['hazard_curve-mean-PGA.csv',
                               'hazard_curve-std-PGA.csv'], case_31.__file__,
                              delta=1E-5)

    def test_case_32(self):
        # source specific logic tree
        self.assert_curves_ok(['hazard_curve-mean-PGA.csv'], case_32.__file__)

    def test_case_33(self):
        # directivity
        self.assert_curves_ok(['hazard_curve-mean-PGA.csv'], case_33.__file__)

    def test_case_34(self):
        # spectral averaging
        self.assert_curves_ok([
            'hazard_curve-mean-AvgSA.csv'], case_34.__file__)

    def test_case_35(self):
        # cluster
        self.assert_curves_ok(['hazard_curve-rlz-000-PGA.csv'],
                              case_35.__file__)

    def test_case_36(self):
        # test with advanced applyToSources and preclassical
        self.run_calc(case_36.__file__, 'job.ini')
        self.assertEqual(self.calc.R, 9)  # there are 9 realizations

    def test_case_37(self):
        # test with amplification function == 1
        self.assert_curves_ok(['hazard_curve-mean-PGA.csv'], case_37.__file__)
        hc_id = str(self.calc.datastore.calc_id)
        # test with amplification function == 2
        self.run_calc(case_37.__file__, 'job.ini',
                      hazard_calculation_id=hc_id,
                      amplification_csv='amplification2.csv')
        [fname] = export(('hcurves/mean', 'csv'), self.calc.datastore)
        self.assertEqualFiles('expected/ampl_curve-PGA.csv', fname)

        # test with amplification function == 2 and no levels
        self.run_calc(case_37.__file__, 'job.ini',
                      hazard_calculation_id=hc_id,
                      amplification_csv='amplification2bis.csv')
        [fname] = export(('hcurves/mean', 'csv'), self.calc.datastore)
        self.assertEqualFiles('expected/ampl_curve-bis.csv', fname)

    def test_case_38(self):
        # BC Hydro GMPEs with epistemic adjustments
        self.assert_curves_ok(["hazard_curve-mean-PGA.csv",
                               "quantile_curve-0.16-PGA.csv",
                               "quantile_curve-0.5-PGA.csv",
                               "quantile_curve-0.84-PGA.csv"],
                              case_38.__file__)

    def test_case_39(self):
        # 0-IMT-weights, pointsource_distance=0 and point_ruptures collapsing
        self.assert_curves_ok([
            'hazard_curve-mean-PGA.csv', 'hazard_curve-mean-SA(0.1).csv',
            'hazard_curve-mean-SA(0.5).csv', 'hazard_curve-mean-SA(2.0).csv',
            'hazard_map-mean.csv'], case_39.__file__, delta=1E-5)

    def test_case_40(self):
        # NGA East
        self.assert_curves_ok([
            'hazard_curve-mean-PGV.csv', 'hazard_map-mean.csv'],
                              case_40.__file__, delta=1E-6)

    def test_case_41(self):
        # SERA Site Amplification Models including EC8 Site Classes and Geology
        self.assert_curves_ok(["hazard_curve-mean-PGA.csv",
                               "hazard_curve-mean-SA(1.0).csv"],
                              case_41.__file__)

    def test_case_42(self):
        # split/filter a long complex fault source with maxdist=1000 km
        self.assert_curves_ok(["hazard_curve-mean-PGA.csv",
                               "hazard_map-mean-PGA.csv"], case_42.__file__)

        # check pandas readability of hmaps-stats
        df = self.calc.datastore.read_df('hmaps-stats', 'site_id',
                                         dict(imt='PGA', stat='mean'))
        self.assertEqual(list(df.columns), ['stat', 'imt', 'poe', 'value'])

    def test_case_43(self):
        # this is a test for pointsource_distance
        self.assert_curves_ok(["hazard_curve-mean-PGA.csv",
                               "hazard_map-mean-PGA.csv"], case_43.__file__)
        self.assertEqual(self.calc.numrups, 499)  # effective ruptures

    def test_case_44(self):
        # this is a test for shift_hypo. We computed independently the results
        # using the same input and a simpler calculator implemented in a
        # jupyter notebook
        self.assert_curves_ok(["hc-shift-hypo-PGA.csv"], case_44.__file__,
                              shift_hypo='true')
        self.assert_curves_ok(["hazard_curve-mean-PGA.csv"], case_44.__file__,
                              shift_hypo='false')

    def test_case_45(self):
        # this is a test for MMI
        self.assert_curves_ok(["hazard_curve-mean-MMI.csv"], case_45.__file__)

    def test_case_46(self):
        # SMLT with applyToBranches
        self.assert_curves_ok(["hazard_curve-mean.csv"], case_46.__file__)

    def test_case_47(self):
        # Mixture Model for Sigma using PEER (2018) Test Case 2.5b
        self.assert_curves_ok(["hazard_curve-rlz-000-PGA.csv",
                               "hazard_curve-rlz-001-PGA.csv"],
                              case_47.__file__, delta=1E05)

    def test_case_48(self):
        # pointsource_distance effects on a simple point source
        self.run_calc(case_48.__file__, 'job.ini')
        tmp = general.gettemp(rst_table(self.calc.datastore['rup/rrup_'],
                                        ['sid0', 'sid1']))
        self.assertEqualFiles('expected/exact_dists.txt', tmp)

        self.run_calc(case_48.__file__, 'job.ini', pointsource_distance='?')
        tmp = general.gettemp(rst_table(self.calc.datastore['rup/rrup_'],
                                        ['sid0', 'sid1']))
        self.assertEqualFiles('expected/approx_dists.txt', tmp)
        # this test shows in detail what happens to the distances in presence
        # of a magnitude-dependent pointsource_distance: just look at the
        # files expected/exact_dists.txt and expected/approx_dists.txt
        # the exact distances for the first site are 54, 53, 53, ... 38, 32 km
        # they decrease with the magnitude, since big magnitude -> big size ->
        # smaller distance from the site.
        # When the pointsource_distance is on, the approximated distances are
        # 55, 55, 55, ..., 38, 32 km: the difference is in the first three
        # values, corresponding to the small magnitudes.
        # For small magnitudes the planar ruptures are replaced by points
        # and thus the distances become larger (and constant).
        # The maximum_distance here is 110 km and the second site
        # was chosen very carefully, so that the exact distance for the highest
        # magnitude is 109 km (within) while the approx distance is 111 km
        # (outside): still the rupture is not discarded because we are in the
        # few-sites regime.
        # In the many-sites regime, small magnitude ruptures at distance close
        # to the maximum_distance may be discarded, instead.
