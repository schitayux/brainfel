frappe.ui.form.on('Sales Invoice', {

    // ------------------------------------------------------------------
    // Helpers compartidos
    // ------------------------------------------------------------------

    _do_certify: function(frm) {
        let prefix = frm.doc.name.substring(0, 4);

        let certify_action = function(motivo_ajuste) {
            frappe.call({
                method: 'brainfel.api.certify_sales_invoice.certify_sales_invoice',
                args: {
                    sales_invoice_name: frm.doc.name,
                    motivo_ajuste: motivo_ajuste
                },
                freeze: true,
                freeze_message: __('Certificando documento FEL...'),
                callback: function(r) {
                    if (!r.exc && r.message && r.message.success) {
                        frappe.msgprint({
                            title: __('Éxito'),
                            indicator: 'green',
                            message: __('Documento certificado correctamente.')
                        });
                        frm.reload_doc();
                    }
                }
            });
        };

        if (prefix === 'NCRE' || prefix === 'NDEB') {
            frappe.prompt({
                label: 'Motivo de Ajuste (Nota)',
                fieldname: 'motivo_ajuste',
                fieldtype: 'Data',
                reqd: 1
            }, function(values) {
                certify_action(values.motivo_ajuste);
            }, 'Certificación FEL', 'Certificar');
        } else {
            certify_action();
        }
    },

    // ------------------------------------------------------------------
    // refresh
    // ------------------------------------------------------------------

    refresh: function(frm) {
        // Quitar botón previo para evitar duplicados
        frm.remove_custom_button(__('Certifica FEL'));
        frm.remove_custom_button('Certifica FEL');
        frm.remove_custom_button(__('PDF'));
        frm.remove_custom_button('PDF');

        // Botón Certifica FEL: solo en documentos enviados sin UUID
        if (frm.doc.docstatus === 1 && !frm.doc.bfel_uuid) {
            frm.add_custom_button(__('Certifica FEL'), function() {
                frm.events._do_certify(frm);
            });
            frm.change_custom_button_type(__('Certifica FEL'), null, 'primary');
        }

        // Botón PDF: si tiene url_pdf configurada en BFEL Settings y tiene bfel_uuid
        if (frm.doc.bfel_uuid) {
            frappe.call({
                method: 'frappe.client.get_value',
                args: {
                    doctype: 'BFEL Settings',
                    filters: { company: frm.doc.company, enabled: 1 },
                    fieldname: 'url_pdf'
                },
                callback: function(r) {
                    if (r.message && r.message.url_pdf) {
                        frm.add_custom_button(__('PDF'), function() {
                            window.open(r.message.url_pdf + frm.doc.bfel_uuid, '_blank');
                        });
                    }
                }
            });
        }

        // ------------------------------------------------------------------
        // Atajos de teclado globales para Sales Invoice
        // Se re-registran en cada refresh para capturar el frm actual.
        // ------------------------------------------------------------------
        $(document).off('keydown.bfel_shortcuts');
        $(document).on('keydown.bfel_shortcuts', function(e) {

            // Solo cuando Sales Invoice es el formulario activo
            if (!cur_frm || cur_frm.doctype !== 'Sales Invoice') return;

            // No interceptar si el foco está en un campo de texto del formulario
            let tag = (document.activeElement || {}).tagName || '';
            if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;

            // ── F3: Guardar → Validar → Certificar (contextual) ───────────
            if (e.key === 'F3') {
                e.preventDefault();
                let f = cur_frm;

                if (f.doc.__islocal || f.is_dirty()) {
                    // Nuevo o con cambios → Guardar borrador
                    f.save();

                } else if (f.doc.docstatus === 0) {
                    // Borrador limpio → Enviar/Validar
                    f.savesubmit();

                } else if (f.doc.docstatus === 1 && !f.doc.bfel_uuid) {
                    // Enviado sin certificar → Certificar FEL
                    f.events._do_certify(f);
                }
                return;
            }

            // ── F4: Imprimir ───────────────────────────────────────────────
            if (e.key === 'F4') {
                e.preventDefault();
                if (cur_frm.doc.docstatus === 0) {
                    frappe.msgprint(__('Guarde o valide el documento antes de imprimir.'));
                } else {
                    cur_frm.print_doc();
                }
                return;
            }

            // ── F9: Nuevo documento ────────────────────────────────────────
            if (e.key === 'F9') {
                e.preventDefault();
                frappe.new_doc('Sales Invoice');
                return;
            }
        });
    },

    // ------------------------------------------------------------------
    // before_cancel
    // ------------------------------------------------------------------

    before_cancel: function(frm) {
        if (frm.doc.bfel_status === '02 Procesada' && frm.doc.bfel_uuid && !frm.doc.__fel_cancelled) {
            frappe.validated = false;

            frappe.prompt({
                label: 'Motivo de anulación FEL',
                fieldname: 'motivo_anulacion',
                fieldtype: 'Data',
                reqd: 1
            }, function(values) {
                frappe.call({
                    method: 'brainfel.api.certify_sales_invoice.cancel_sales_invoice_fel',
                    args: {
                        sales_invoice_name: frm.doc.name,
                        motivo_anulacion: values.motivo_anulacion
                    },
                    freeze: true,
                    freeze_message: __('Anulando en portal FEL...'),
                    callback: function(r) {
                        if (!r.exc && r.message && r.message.success) {
                            frappe.msgprint({
                                title: __('Éxito'),
                                indicator: 'green',
                                message: r.message.message || __('Documento anulado correctamente en FEL.')
                            });
                            frm.doc.__fel_cancelled = true;
                            frm.save('cancel');
                        }
                    }
                });
            }, 'Anulación FEL', 'Anular');
        }
    }
});
