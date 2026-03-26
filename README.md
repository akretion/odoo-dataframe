

# Dataframe with Odoo
<!-- /!\ Non OCA Context : Set here the badge of your runbot / runboat instance. -->
[![Pre-commit Status](https://github.com/akretion/odoo-dataframe/actions/workflows/pre-commit.yml/badge.svg?branch=18.0)](https://github.com/akretion/odoo-dataframe/actions/workflows/pre-commit.yml?query=branch%3A18.0)
[![Build Status](https://github.com/akretion/odoo-dataframe/actions/workflows/test.yml/badge.svg?branch=18.0)](https://github.com/akretion/odoo-dataframe/actions/workflows/test.yml?query=branch%3A18.0)
[![codecov](https://codecov.io/gh/akretion/odoo-dataframe/branch/18.0/graph/badge.svg)](https://codecov.io/gh/akretion/odoo-dataframe)
<!-- /!\ Non OCA Context : Set here the badge of your translation instance. -->

<!-- /!\ do not modify above this line -->

Use polars dataframe to process data before using in Odoo

<!-- /!\ do not modify below this line -->

<!-- prettier-ignore-start -->

[//]: # (addons)

Available addons
----------------
addon | version | maintainers | summary
--- | --- | --- | ---
[df_process](df_process/) | 18.0.1.0.0 | <a href='https://github.com/bealdav'><img src='https://github.com/bealdav.png' width='32' height='32' style='border-radius:50%;' alt='bealdav'/></a> | Common methods to import data from dataframe
[df_source](df_source/) | 18.0.1.0.0 | <a href='https://github.com/bealdav'><img src='https://github.com/bealdav.png' width='32' height='32' style='border-radius:50%;' alt='bealdav'/></a> | Base module for file or database sources for DataFrame
[file_df](file_df/) | 18.0.2.0.0 | <a href='https://github.com/bealdav'><img src='https://github.com/bealdav.png' width='32' height='32' style='border-radius:50%;' alt='bealdav'/></a> | Allow to create a Polars dataframe from file and process it according to rules.
[record_field_log](record_field_log/) | 18.0.1.0.0 | <a href='https://github.com/bealdav'><img src='https://github.com/bealdav.png' width='32' height='32' style='border-radius:50%;' alt='bealdav'/></a> | Reports issues on odoo records to be analyzed later.

[//]: # (end addons)

<!-- prettier-ignore-end -->

## Licenses

This repository is licensed under [AGPL-3.0](LICENSE).

However, each module can have a totally different license, as long as they adhere to Akretion
policy. Consult each module's `__manifest__.py` file, which contains a `license` key
that explains its license.

----
<!-- /!\ Non OCA Context : Set here the full description of your organization. -->
