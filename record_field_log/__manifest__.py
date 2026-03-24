{
    "name": "Record field Logs",
    "version": "18.0.1.0.0",
    "author": "Akretion",
    "license": "LGPL-3",
    "website": "https://github.com/akretion/odoo-dataframe",
    "summary": "Reports issues on odoo records to be analyzed later.",
    "depends": [
        "base",
    ],
    "maintainers": ["bealdav"],
    "data": [
        "security/group.xml",
        "security/ir.model.access.xml",
        "views/field_log.xml",
    ],
    "installable": True,
}
