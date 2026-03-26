from odoo import fields, models


class DfSource(models.Model):
    _inherit = "df.source"

    except_logged = fields.Boolean(
        help="Indicate if exception are logged with this source"
    )

    def _get_touchy_fields_to_import(self):
        """inherit me
         Some fields may break your process and could be benefit
         of a specific process. We have to know them
        i.e. {"res.partner": ["vat"]}
        """
        # return {"res.partner": ["vat", "siret"], "product.product": ["barcode"]}
        return {}
