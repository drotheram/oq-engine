# -*- coding: utf-8 -*-
"""
Top-level managers for computation classes.
"""

from opengem import hazard
from opengem import logs
from opengem import kvs
from opengem import risk
from opengem import shapes

from opengem.parser import vulnerability
from opengem.risk import classical_psha_based
from opengem.risk import probabilistic_event_based

logger = logs.RISK_LOG

# TODO (ac): This class is not covered by unit tests...
class ClassicalPSHABasedLossRatioCalculator(object):
    """Computes loss ratio curves based on hazard curves and 
    exposure portfolios"""

    def __init__(self, job_id, block_id, memcache_client=None):
        """ Prepare the calculator for computations"""

        self.job_id = job_id
        self.block_id = block_id

        self.vuln_curves = \
                vulnerability.load_vulnerability_curves_from_kvs(self.job_id)

        # self.vuln_curves is a dict of {string: Curve}
        logger.debug("ProbabilisticLossRatioCalculator init: vuln curves are")

        for k,v in self.vuln_curves.items():
            logger.debug("%s: %s" % (k, v))
 
    def compute_loss_ratio_curve(self, gridpoint):
        """ Returns the loss ratio curve for a single gridpoint"""

        # check in kvs if hazard and exposure for gridpoint are there
        kvs_key_hazard = kvs.generate_product_key(self.job_id, 
            hazard.HAZARD_CURVE_KEY_TOKEN, self.block_id, gridpoint)
       
        hazard_curve_json = self.get_client(binary=False).get(kvs_key_hazard)
        logger.debug("hazard curve as JSON: %s" % hazard_curve_json)
 
        hazard_curve = shapes.EMPTY_CURVE
        hazard_curve.from_json(hazard_curve_json)

        logger.debug("hazard curve at key %s is %s" % (kvs_key_hazard, 
                                                    hazard_curve.values))
        if hazard_curve is None:
            logger.debug("no hazard curve found")
            return None

        kvs_key_exposure = kvs.generate_product_key(self.job_id, 
            risk.EXPOSURE_KEY_TOKEN, self.block_id, gridpoint)
        
        asset = kvs.get_value_json_decoded(kvs_key_exposure)

        logger.debug("asset at key %s is %s" % (kvs_key_exposure, asset))

        if asset is None:
            logger.debug("no asset found")
            return None

        logger.debug("compute method: vuln curves are")
        for k,v in self.vulnerability_curves.items():
            logger.debug("%s: %s" % (k, v.values))

        vulnerability_curve = \
            self.vulnerability_curves[asset['VulnerabilityFunction']]

        # selected vuln function is Curve
        return classical_psha_based.compute_loss_ratio_curve(
            vulnerability_curve, hazard_curve)
    
    def compute_loss_curve(self, gridpoint, loss_ratio_curve):
        """Return the loss curve based on loss ratio and exposure."""
        
        if loss_ratio_curve is None:
            return None

        kvs_key_exposure = kvs.generate_product_key(self.job_id,
            risk.EXPOSURE_KEY_TOKEN, self.block_id, gridpoint)

        asset = kvs.get_value_json_decoded(kvs_key_exposure)

        if asset is None:
            return None

        return classical_psha_based.compute_loss_curve(
            loss_ratio_curve, asset['AssetValue'])

class ProbabilisticEventBasedCalculator(object):
    """Compute loss ratio and loss curves using the probabilistic event
    based approach."""
    
    def __init__(self, job_id, block_id):
        self.job_id = job_id
        self.block_id = block_id

        self.vuln_curves = \
                vulnerability.load_vulnerability_curves_from_kvs(self.job_id)

    def compute_loss_ratio_curve(self, column, row ): # site_id
        """Compute the loss ratio curve for a single site."""
        key_exposure = kvs.generate_product_key(self.job_id,
            risk.EXPOSURE_KEY_TOKEN, column, row)
        
        asset = kvs.get_value_json_decoded(key_exposure)

        vuln_function = self.vuln_curves[asset["VulnerabilityFunction"]]

        key_gmf = kvs.generate_product_key(self.job_id, 
                risk.GMF_KEY_TOKEN, column, row)
       
        gmf = kvs.get_value_json_decoded(key_gmf)
        return probabilistic_event_based.compute_loss_ratio_curve(
                vuln_function, gmf)

    def compute_loss_curve(self, column, row, loss_ratio_curve):
        """Compute the loss curve for a single site."""
        key_exposure = kvs.generate_product_key(self.job_id,
            risk.EXPOSURE_KEY_TOKEN, column, row)
        
        asset = kvs.get_value_json_decoded(key_exposure)
        
        if asset is None:
            return None
        
        return loss_ratio_curve.rescale_abscissae(asset["AssetValue"])

def compute_loss(loss_curve, pe_interval):
    """Interpolate loss for a specific probability of exceedance interval"""
    loss = classical_psha_based.compute_conditional_loss(loss_curve, 
                                                         pe_interval)
    return loss
