from odoo.upgrade import util

def migrate(cr, version):
    if not version:
        return

    # 1. ELIMINACIÓN DE VISTAS (Basado en los CRITICAL de ir_ui_view)
    views_to_remove = [
        "l10n_ar_withholding.withholdings_report_general",
        "l10n_ar_withholding.view_withholdings_report_form",
        "l10n_ar_withholding.report_payment_withholding",
        "l10n_ar_withholding.report_payment_withholding_document",
        "l10n_ar_withholding.view_account_move_perceptions_form",
        "l10n_ar_withholding.view_account_export_sicore",
        "l10n_ar_withholding.view_account_export_sicore_form",
        "l10n_ar_withholding.withholding_report_account_paymentp_form",
        "l10n_ar_withholding.view_afip_tabla_ganancias_alicuotasymontos_tree",
        "l10n_ar_withholding.view_afip_tabla_ganancias_escala_tree",
        "l10n_ar_withholding.view_company_inherit_form",
        "l10n_ar_withholding.view_partner_property_form",
        "l10n_ar_withholding.view_account_payment_group_form_supplier",
        "l10n_ar_withholding.view_account_payment_group_form",
        "l10n_ar_withholding.view_account_payment_from_group_tree",
        "l10n_ar_withholding.view_account_payment_tree",
        "l10n_ar_withholding.view_account_payment_form_automatic",
        "l10n_ar_withholding.view_account_tax_search",
    ]

    for view_xmlid in views_to_remove:
        util.remove_view(cr, view_xmlid)

    # 2. ELIMINACIÓN DE CAMPOS EN MODELOS PERSISTENTES (res.users / res.partner)
    fields_to_remove = [
        ('res.users', 'empleador_padron'),
        ('res.users', 'actividad_monotributo_padron'),
        ('res.users', 'monotributo_padron'),
        ('res.users', 'integrante_soc_padron'),
        ('res.users', 'imp_iva_padron'),
        ('res.users', 'imp_ganancias_padron'),
        ('res.users', 'estado_padron'),
        ('res.users', 'afip_responsability_type_id'),
        ('res.users', 'start_date'),
        ('res.users', 'gross_income_jurisdiction_ids'),
        ('res.users', 'gross_income_type'),
        ('res.users', 'gross_income_number'),
        ('res.users', 'default_regimen_ganancias_id'),
        ('res.users', 'drei'),
        ('res.users', 'iibb_number'),
    ]

    for model, field in fields_to_remove:
        util.remove_field(cr, model, field)

    # 3. ELIMINACIÓN DE CAMPOS EN MODELOS TRANSITORIOS (Wizards/Reports)
    # Estos son los que causaron el UpgradeError final
    transient_fields = [
        ('ar.withholdings.reports', 'write_date'),
        ('ar.withholdings.reports', 'write_uid'),
        ('ar.withholdings.reports', 'create_date'),
        ('ar.withholdings.reports', 'create_uid'),
        ('ar.withholdings.reports', 'id'),
        ('ar.withholdings.reports', 'date_to'),
        ('ar.withholdings.reports', 'date_from'),
        ('ar.withholdings.reports', 'type_report'),
        ('account.export.sicore', 'write_date'), # El que rompió el log al final
    ]

    for model, field in transient_fields:
        util.remove_field(cr, model, field)
