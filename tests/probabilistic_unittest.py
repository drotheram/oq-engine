# -*- coding: utf-8 -*-
# vim: tabstop=4 shiftwidth=4 softtabstop=4

import os
import unittest

from openquake.risk.job.probabilistic import ProbabilisticEventMixin
from openquake.parser import exposure
from utils import test


TEST_FILE = 'exposure-portfolio.xml'


class EpsilonTestCase(unittest.TestCase):
    """Tests the method:`epsilon` in class:`ProbabilisticEventMixin`"""

    def setUp(self):
        self.exposure_parser = exposure.ExposurePortfolioFile(
            os.path.join(test.SCHEMA_EXAMPLES_DIR, TEST_FILE))
        self.mixin = ProbabilisticEventMixin()

    def test_uncorrelated(self):
        """In case of uncorrelated jobs we should obtain an independent
        `epsilon` value for each asset."""
        samples = []
        for _, asset in self.exposure_parser:
            sample = self.mixin.epsilon(asset)
            self.assertTrue(
                sample not in samples,
                "%s is already in %s" % (sample, samples))
            self.assertTrue(
                isinstance(sample, float), "Invalid sample (%s)" % sample)
            samples.append(sample)

    def test_correlated(self):
        """In case of correlated jobs we should obtain the same
        `epsilon` value for assets of the same building typology."""
        samples = dict()
        self.mixin.__dict__['ASSET_CORRELATION'] = "perfect"
        for _, asset in self.exposure_parser:
            sample = self.mixin.epsilon(asset)
            category = asset['structureCategory']
            # This is either the first time we see this structure category or
            # the sample is identical to the one originally drawn for this
            # structure category.
            if category not in samples:
                samples[category] = sample
            else:
                self.assertTrue(sample == samples[category])
        # Make sure we used at least two structure categories in this test.
        self.assertTrue(len(samples.keys()) > 1)
        # Are all samples valid values?
        for category, sample in samples.iteritems():
            self.assertTrue(
                isinstance(sample, float),
                "Invalid sample (%s) for category %s" % (sample, category))
