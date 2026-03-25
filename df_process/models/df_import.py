import logging
from collections import defaultdict

import polars as pl
import polars.selectors as cs

from odoo import models
from odoo.exceptions import ValidationError

logger = logging.getLogger(__name__)


class DfImport(models.AbstractModel):
    _inherit = "df.import"

    def _odoo_df_upsert(self, df, source):
        """Update/Insert: Either create or write records according to:
        - no 'id' column => CREATE
        - 'id' column with unknown uidstring => CREATE with new uidstring
        - 'id' column with known uidstring => WRITE
        """
        df = self._odoo_df_process(source, df)
        created_recs, updated_recs = False, False
        df = self._remove_useless_columns(df, source)
        map_id = getattr(source, "map_id", False)
        if map_id and map_id.matching_field_id:
            df_create, df_write = self._split_create_update_df(df, source)
            updated_recs = self._update_records_from_df(df_write, source)
        else:
            df_create, df_write = self._id_column_management(df)
        if not created_recs and not df_create.is_empty():
            vals_list = df_create.to_dicts()
            try:
                # We try all at once for performance, but if it fails
                # we try one by one to identify the problem record(s)
                created_recs = self.env[source.model].create(vals_list)
            except Exception as err:
                logger.warning(
                    "Error during bulk creation, trying one by one "
                    + f"to identify problematic record(s): {err}"
                )
                for vals in vals_list:
                    try:
                        self.env[source.model].create(vals)
                    except Exception as err:
                        row_viewer = self.env["df.import"]._convert_flat_dict_to_ini(
                            vals
                        )
                        raise ValidationError(
                            f"Error during import of {source.model} : {err}"
                            + f"{vals}\n\n{row_viewer}"
                        ) from err
            if "id" in df_create.columns:
                self._add_metadata(created_recs, df_create, source)
        if not updated_recs and not df_write.is_empty():
            updated_recs = self._update_records_from_df(df_write, source)
        return created_recs, updated_recs

    def _update_records_from_df(self, df, source):
        record_ids = []
        if df.is_empty():
            return False
        # if id colmun is a string we have a specific behavior
        id_string = df["id"].dtype == pl.String
        for vals in df.to_dicts():
            id_ = vals.pop("id")
            if id_string:
                record = self.env.ref(id_)
                record_ids.append(record.id)
            else:
                record_ids.append(id_)
                record = self.env[source.model].browse(id_)
            record.write(vals)
        return self.env[source.model].browse(record_ids)

    def _split_create_update_df(self, df, source):
        """Separate data in two dataframes for create and write
        based on mapping with keys combination:

        - df creation from mapping dict
        - dataframes join
        - write on records with vals from df, record id from mapping

        Here an example for
        ┌───────────┬────────────┬────────┬───────┐
        │ name      ┆ start_date ┆ ref    ┆ any   │
        ╞═══════════╪════════════╪════════╪═══════╡
        │ LAS000012 ┆ 2022-07-01 ┆ 7BC71D ┆ sale  │
        │ ALL000005 ┆ 2026-01-01 ┆ 8390ED ┆ sale  │
        │ ALL000005 ┆ 2023-01-01 ┆ 7BC00D ┆ sale  │
        └───────────┴────────────┴────────┴───────┘
        key is 'ref' column here
        """
        keys, mapping = self._get_mapping_from_key_combination(df, source)
        # ┌─────┬─────────┐
        # │ id  ┆ ref     │  df_mapping contains all keys and id column
        # ╞═════╪═════════╡
        # │ 51  ┆ 7BC71D  │
        # └─────┴─────────┘
        df_mapping = pl.DataFrame([{"id": k, **v} for k, v in mapping.items()])
        # id column is in df_mapping
        df_write = pl.DataFrame()
        if not df_mapping.is_empty():
            # joined data dataframes becomes
            # ┌───────────┬────────────┬────────┬───────┬───────┐
            # │ name      ┆ start_date ┆ ref    ┆ any   ┆ id    │
            # ╞═══════════╪════════════╪════════╪═══════╪═══════╡
            # │ LAS000012 ┆ 2022-07-01 ┆ 7BC71D ┆ sale  ┆ 51    │
            # │ ALL000005 ┆ 2026-01-01 ┆ 8390ED ┆ sale  ┆ null  │
            # │ ALL000005 ┆ 2023-01-01 ┆ 7BC00D ┆ sale  ┆ null  │
            # └───────────┴────────────┴────────┴───────┴───────┘
            df = df.join(df_mapping, on=keys, how="left")
            # df_write is
            # ┌───────────┬────────────┬────────┬───────┬─────┐
            # │ name      ┆ start_date ┆ ref    ┆ any   ┆ id  │
            # ╞═══════════╪════════════╪════════╪═══════╪═════╡
            # │ LAS000012 ┆ 2022-07-01 ┆ 7BC71D ┆ sale  ┆ 51  │
            # └───────────┴────────────┴────────┴───────┴─────┘
            df_write = df.filter(pl.col("id").is_not_null())
            # we don't need keys columns anymore for write, we don't want to write them
            df_write = df_write.drop(keys)
        if "id" in df.columns:
            # df_create is
            # ┌───────────┬────────────┬────────┬──────┐
            # │ name      ┆ start_date ┆ ref    ┆ any  │
            # ╞═══════════╪════════════╪════════╪══════╡
            # │ ALL000005 ┆ 2026-01-01 ┆ 8390ED ┆ sale │
            # │ ALL000005 ┆ 2023-01-01 ┆ 7BC00D ┆ sale │
            # └───────────┴────────────┴────────┴──────┘
            df_create = df.filter(pl.col("id").is_null()).drop("id")
        else:
            df_create = df
        return df_create, df_write

    def _get_mapping_from_key_combination(self, df, source):
        """
        - search records in erp for keys combinations: mapping = {record.id: record}
        - populate mapping with all keys:
                mapping = {record.id: {key: record[key].id or record[key]}}
        """
        # i.e. keys are [city_id, 'zip']
        keys = sorted([x.name for x in source.map_id.matching_field_id.field_ids])
        if any([x not in df.columns for x in keys]):
            # TODO move this check in file_df module
            raise ValidationError(
                f"Some keys '{keys}' are not in df columns {df.columns}"
            )
        # In case of duplicate keys in model, we can have surprising results,
        # we consider here that keys combination are unique
        # TODO can be improved with non unique scenarii
        domain = [(key, "!=", False) for key in keys]
        mapping = {x.id: x for x in self.env[source.model].search(domain)}
        # mapping'll be {id1: {'city_id': val1, 'zip': val2}, id2: {...}
        for record in mapping.values():
            mapping[record.id] = {
                key: getattr(record[key], "_fields", False)
                # in case of many2one
                and record[key].id
                # else simple field
                or record[key]
                for key in keys
            }
        return keys, mapping

    def _id_column_management(self, df):
        """If 'id' is in colmuns, we consider it's a uidstring"""
        module = self.env["df.source"]._get_uidstring_module_name()
        df_create, df_write = pl.DataFrame({}), pl.DataFrame({})
        if "id" in df.select(cs.string()).columns:
            # id column is a string, needs to be a full uidstring
            # prefix "module." to uidstring id no "." in uidstring
            df = df.with_columns(
                pl.when(~pl.col("id").str.contains(r"\."))
                .then(pl.lit(module + ".") + pl.col("id"))
                .otherwise(pl.col("id"))
                .alias("id")
            )
            known_imd = self._get_ir_model_data_from_column(df, "id")
            # known model data are written
            df_write = df.filter(pl.col("id").is_in(known_imd))
            # unknown are created
            df_create = df.filter(~pl.col("id").is_in(known_imd))
        else:
            # only new records to create, no uidstring management
            df_create = df
        return df_create, df_write

    def _get_ir_model_data_from_column(self, df, column):
        """Get existing ir.model.data from dataframe column containing uidstring"""
        imd = defaultdict(list)
        # Group ir.model.data by module
        for x in df.get_column(column).unique().to_list():
            imd[x[: x.index(".")]].append(x[x.index(".") + 1 :])
        known_imd = []
        # Search for existing ir.model.data
        for module, names in imd.items():
            known_imd.extend(
                [
                    f"{module}.{x.name}"
                    for x in self.env["ir.model.data"].search(
                        [
                            ("module", "=", module),
                            ("name", "in", names),
                        ]
                    )
                ]
            )
        return known_imd

    def _odoo_df_process(self, source, df):
        """TODO
        - process df to map m2m
        """
        model = source.model
        m2os, m2ms = self._get_relational_fields(model, df.columns)
        if m2os:
            for m2o in m2os:
                if not df[m2o.name].dtype.is_numeric():
                    df = self._process_m2o_field(m2o, df)
        df = self._substitute_uid_string(df)
        # Date transformation
        df = self._convert_date(df)
        return df

    def _get_m2o_matching_field(self):
        """i.e. {"res.partner": "ref"}
        TODO : remove use case because of map_id.matching_field_id
        """
        return {}

    def _process_m2o_field(self, m2o, df):
        """Mimic base_import_match behavior for m2o field,
        only if matching field is configured"""
        field_name = self._get_m2o_matching_field().get(m2o.relation)
        if not field_name:
            # TODO collect exceptions and log in odoo
            return df
        # odoo data: vals_ids is {field_value: record_id} from field.relation
        vals_ids = {
            x[field_name]: x.id
            for x in self.env[m2o.relation].search([(field_name, "!=", False)])
        }
        # dataframe field values unknown in odoo
        unknown = df.filter(~pl.col(m2o.name).is_in(vals_ids.keys()))
        df = df.with_columns(pl.col(m2o.name).replace(vals_ids).cast(pl.Int64))
        if not unknown.is_empty():
            logger.warning("Unmatching values", unknown)
            raise ValidationError(
                f"Unknown values for '{m2o.name}' for model {m2o.relation}: "
                + f"{unknown.get_column(m2o.name).unique().to_list()}"
            )
        return df

    def _get_relational_fields(self, model, columns):
        fields_ = self.env["ir.model.fields"].search(
            [("model_id.model", "=", model), ("ttype", "in", ("many2one", "many2many"))]
        )
        m2o = fields_.filtered(lambda x: x.ttype == "many2one" and x.name in columns)
        m2m = fields_.filtered(lambda x: x.ttype == "many2many" and x.name in columns)
        return m2o, m2m

    def _convert_date(self, df):
        "TODO improve date management with better format detection and error handling"
        for field in [x for x in df.columns if "date" in x]:
            # TODO improve date management
            format_ = "%d/%m/%Y"
            size = len(df.get_column(field).to_list()[0])
            if size == 16:
                format_ = "%d/%m/%Y %H:%M"
            elif size == 19:
                format_ = "%d/%m/%Y %H:%M:%S"
            df = df.with_columns(
                pl.col(field).str.strptime(pl.Date, format=format_).alias(field)
            )
        return df

    def _substitute_uid_string(self, df):
        """Replace xml_id by the corresponding id in Odoo,
        only for columns which contains "base." string value
        TODO improve xmlid detection in a more generic way.
        """
        uid_cols = [
            # filtering string columns
            col
            for col in df.select(cs.string()).columns
            # checking if at least one value in the column contains "base."
            if df.select(pl.col(col).str.contains(r"base\.").any()).item()
        ]
        uidstrings = []
        for col in uid_cols:
            uidstrings.extend(
                [x for x in df.get_column(col).to_list() if x and "base." in x]
            )
        mapping = {}
        for string in uidstrings:
            record = self.env.ref(string, raise_if_not_found=False)
            if record:
                mapping[string] = record.id
            else:
                # TODO report this event in odoo: record_field_log
                logger.warning(f"Unmatching xml_id: '{string}'")
        for col in uid_cols:
            df = df.with_columns(pl.col(col).replace(mapping).cast(pl.Int64))
        return df

    def _add_metadata(self, records, df_create, source):
        """uidstring / xmlid creation"""
        id_vals = df_create.get_column("id").to_list()
        idx, imd = 0, []
        for rec in records:
            module_and_name = id_vals[idx].split(".")
            # imd is ir_model_data
            imd.append(
                {
                    "model": source.model,
                    "module": module_and_name[0],
                    "name": module_and_name[1],
                    "res_id": rec.id,
                }
            )
            idx += 1
        self.env["ir.model.data"].create(imd)

    def _remove_useless_columns(self, df, source):
        df = df.drop(
            [x for x in df.columns if x not in self.env[source.model]._fields.keys()]
        )
        return df
