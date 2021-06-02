# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
import datetime
from odoo.exceptions import UserError, ValidationError, Warning
import math
from dateutil.relativedelta import relativedelta
from odoo.tools.float_utils import float_compare, float_is_zero, float_round
import pytz


class ResPartner(models.Model):
    _inherit = "res.partner"
    clint_num = fields.Char('ID Number', copy=False)
    id_issue_at = fields.Char('ID Issued from', copy=False)
    id_date = fields.Date('ID Expiry Date')
    license_num = fields.Char('License Number')
    license_issue_at = fields.Char('License Issued from', copy=False)

    license_date = fields.Date('License Expiry Date')
    license_type = fields.Selection([('private', 'Private'), ('public', 'Public'), ('international', 'International'), ]
                                    ,
                                    string='License Type')
    black_list = fields.Selection([('active', 'Active'), ('inactive', 'Inactive')], string='Black List',
                                  default='inactive',
                                  track_visibility="onchange")
    country_id = fields.Many2one(
        'res.country', 'Nationality (Country)', tracking=True)
    _sql_constraints = [
        (
            'id_unique', 'UNIQUE (clint_num)',
            'ID Number must be unique'),
        ('license_unique', 'UNIQUE (license_num)',
         'License Number must be unique'),
    ]


class ProductProductFleet(models.Model):
    _inherit = 'product.product'

    afford_amount = fields.Float(string="Afford Amount", default=0.00)
    fleet_status = fields.Selection([
        ('available', 'Available'),
        ('in_use', 'In Use'),
        ('p_maintenance', 'Preventive Maintenance'),
        ('c_maintenance', 'Corrective Maintenance')], string='Status', default='available'
    )
    odometer = fields.Float(related="fleet_id.odometer", string='Last Odometer',
                            help='Odometer measure of the vehicle at the moment of this log')
    km_allowed = fields.Float(string='KM Allowed', help='The number of kilometers allowed')
    extra_km_price = fields.Float(string='Extra KM Price')


class FleetVehicleInherit(models.Model):
    _inherit = 'fleet.vehicle'

    afford_amount = fields.Float(string="Afford Amount", default=0.00, related="product_id.afford_amount", store=True)
    km_allowed = fields.Float(string="KM Allowed", default=0.00, related="product_id.km_allowed", store=True)
    extra_km_price = fields.Float(string="Extra KM Price", default=0.00, related="product_id.extra_km_price", store=True)


class RentalRenew(models.TransientModel):
    _inherit = 'rental.renew'

    def extend_rental(self):
        rental = self.env['rental.order'].browse(self._context.get('active_id'))
        if self.date <= rental.end_date:
            raise UserError(_('The Extended Date must be after the contract end date !!!'))
        rental.end_date = self.date
        duration_dict = rental._compute_duration_vals(rental.start_date, rental.end_date)
        if rental.rental_initial_type == 'days':
            rental.extended_period = duration_dict['day'] - rental.rental_initial
        elif rental.rental_initial_type == 'weeks':
            rental.extended_period = duration_dict['week'] - rental.rental_initial
        elif rental.rental_initial_type == 'months':
            rental.extended_period = duration_dict['month'] - rental.rental_initial
        return


class RentalOrder(models.Model):
    _inherit = 'rental.order'

    additional_driver_active = fields.Boolean('Add Additional Driver')
    additional_driver_id = fields.Many2one('res.partner', string='Additional Driver')
    rental_initial_type = fields.Selection(string="Initial Terms Type", selection=[
        ('days', 'Days'),
        ('weeks', 'Weeks'),
        ('months', 'Months')], required=True, default="days", copy=False)
    state = fields.Selection([
        ('draft', 'Quotation'),
        ('confirm', 'Confirmed Rental'),
        ('checking', 'Checking'),
        ('close', 'Closed Rental'),
    ], string='Status', readonly=True, default='draft')
    outgoing_done = fields.Boolean('Vehicle delivered', default=False)
    incoming_done = fields.Boolean('Vehicle received', default=False)
    extended_period = fields.Integer(string='Extended Period', readonly=True)
    extended_period_type = fields.Selection(string="Extended Period Type", selection=[
        ('days', 'Days'),
        ('weeks', 'Weeks'),
        ('months', 'Months')], readonly=True, default="days", copy=False)
    tamm_auth = fields.Char(string="Tamm Authorization", required=True, track_visibility='onchange')
    shmoos = fields.Boolean('Shmoos Checking', default=False, required=True, track_visibility='onchange')
    days_duration = fields.Integer(string='Duration in days')
    km_diff = fields.Integer(string='Kilometer difference')
    @api.model
    def create(self, vals):
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code('rental.order') or 'New'
        partner = self.env['res.partner'].browse(vals.get('partner_id'))
        if partner.black_list == 'active':
            raise UserError(_('The customer is included in the blacklist'))
        if vals.get('additional_driver_id'):
            additional_driver = self.env['res.partner'].browse(vals.get('additional_driver_id'))
            if additional_driver.black_list == 'active':
                raise UserError(_('The Additional Driver is included in the blacklist'))
        # Makes sure partner_invoice_id', 'partner_shipping_id' and 'pricelist_id' are defined
        if any(f not in vals for f in ['partner_invoice_id', 'partner_shipping_id', 'pricelist_id']):
            addr = partner.address_get(['delivery', 'invoice'])
            vals['partner_invoice_id'] = vals.setdefault('partner_invoice_id', addr['invoice'])
            vals['partner_shipping_id'] = vals.setdefault('partner_shipping_id', addr['delivery'])
            vals['pricelist_id'] = vals.setdefault('pricelist_id',
                                                   partner.property_product_pricelist and partner.property_product_pricelist.id)

        if not vals.get('start_date'):
            vals['start_date'] = datetime.datetime.today().date()
        if vals.get('rental_bill_freq_type') == 'days':
            calc = vals['rental_bill_freq'] / 30
            if calc > vals['rental_initial']:
                raise Warning('Invoice cycle period should not be grater then total rental period')
        if vals.get('rental_bill_freq_type') == 'months':
            if vals['rental_bill_freq'] > vals['rental_initial']:
                raise Warning('Invoice cycle period should not be grater then total rental period')

        result = super(RentalOrder, self).create(vals)
        return result

    def write(self, vals):
        if vals.get('partner_id'):
            partner = self.env['res.partner'].browse(vals.get('partner_id'))
            if partner.black_list == 'active':
                raise UserError(_('The customer is included in the blacklist'))
        if vals.get('additional_driver_active') == False:
            if not vals.get('additional_driver_active'):
                vals['additional_driver_id'] = False
        else:
            if vals.get('additional_driver_id'):
                additional_driver = self.env['res.partner'].browse(vals.get('additional_driver_id'))
                if additional_driver.black_list == 'active':
                    raise UserError(_('The Additional Driver is included in the blacklist'))
        return super(RentalOrder, self).write(vals)

    @api.onchange('end_date')
    def _onchange_end_date(self):
        for rental in self:
            if rental.start_date and rental.end_date:
                duration_dict = self._compute_duration_vals(rental.start_date, rental.end_date)
                if rental.rental_initial_type == 'days':
                    rental.rental_initial = duration_dict['day']
                elif rental.rental_initial_type == 'weeks':
                    rental.rental_initial = duration_dict['week']
                elif rental.rental_initial_type == 'months':
                    rental.rental_initial = duration_dict['month']

    @api.model
    def _compute_duration_vals(self, pickup_date, return_date):
        duration = return_date - pickup_date
        vals = dict(hour=(duration.days * 24 + duration.seconds / 3600))
        vals['day'] = math.ceil(vals['hour'] / 24)
        vals['week'] = math.ceil(vals['day'] / 7)
        duration_diff = relativedelta(return_date, pickup_date)
        months = 1 if duration_diff.days or duration_diff.hours or duration_diff.minutes else 0
        months += duration_diff.months
        months += duration_diff.years * 12
        vals['month'] = months
        return vals

    def _create_km_invoice(self, product):
        inv_obj = self.env['account.move']
        inv_line = []

        for rental in self:
            inv_name = rental.name + "/EKM"
            for line in rental.rental_line:
                account_id = False
                if line.product_id.id:
                    account_id = line.product_id.categ_id.property_account_income_categ_id.id
                if not account_id:
                    raise UserError(
                        _(
                            'There is no income account defined for this product: "%s". You may have to install a chart of account from Accounting app, settings menu.') % \
                        (line.product_id.name,))

                inv_line.append((0, 0, {
                                    'name': product.description_rental or " ",
                                    'account_id': account_id,
                                    'price_unit': line.product_id.extra_km_price,
                                    'quantity': rental.km_diff,
                                    'rental_line_ids': [(6, 0, [line.id])],
                                    'product_uom_id': product.uom_id.id,
                                    'product_id': product.id,
                                    'tax_ids': [(6, 0, line.tax_id.ids)],
                                }))
            invoice = inv_obj.create({
                'name': rental.client_order_ref or inv_name or " ",
                'invoice_origin': rental.name or " ",
                'move_type': 'out_invoice',
                'rental_id': rental.id,
                'ref': False,
                'partner_id': rental.partner_invoice_id.id,
                'invoice_line_ids': inv_line,
                'currency_id': rental.pricelist_id.currency_id.id,
                'user_id': rental.user_id.id,
                'from_rent_order': True,
            })
        return invoice

    def _create_invoice_with_saleable(self, force=False):
        inv_obj = self.env['account.move']
        picking_rental_obj = self.env['stock.picking'].search([('origin', '=', self.name)])
        inv_line = []

        for rental in self:
            inv_name = rental.name
            start_date = rental.start_date
            end_date = rental.end_date
            for line in rental.rental_line:
                account_id = False
                if line.product_id.id:
                    account_id = line.product_id.categ_id.property_account_income_categ_id.id
                if not account_id:
                    raise UserError(
                        _(
                            'There is no income account defined for this product: "%s". You may have to install a chart of account from Accounting app, settings menu.') % \
                        (line.product_id.name,))
                if picking_rental_obj:
                    for picking in picking_rental_obj:
                        if picking.state == 'done':
                            # picking_done = pytz.utc.localize(picking.date_done).astimezone()
                            # picking_done = picking_done.replace(tzinfo=None)
                            duration_dict = self._compute_duration_vals(picking.date_done, fields.datetime.now())
                            actual_days = duration_dict['day']
                            if rental.rental_initial_type == 'days':
                                rental_days = rental.rental_initial
                            elif rental.rental_initial_type == 'weeks':
                                rental_days = rental.rental_initial * 7
                            elif rental.rental_initial_type == 'months':
                                rental_days = rental.rental_initial * 30
                            if actual_days > rental_days:
                                rental.update({'days_duration': actual_days})
                                diff_days = actual_days - rental_days
                                initial_end_date = rental.end_date - relativedelta(days=diff_days)
                                start_date = initial_end_date + relativedelta(days=1)
                                end_date = datetime.datetime.today().date()
                                inv_name += "EX"
                                inv_line.append((0, 0, {
                                    'name': line.product_id.description_rental or inv_name or " ",
                                    'account_id': account_id,
                                    'price_unit': line.price_unit,
                                    'quantity': diff_days,
                                    'rental_line_ids': [(6, 0, [line.id])],
                                    'product_uom_id': line.product_id.uom_id.id,
                                    'product_id': line.product_id.id,
                                    'tax_ids': [(6, 0, line.tax_id.ids)],
                                }))
                else:
                    inv_line.append((0, 0, {
                        'name': line.product_id.description_rental or line.name or " ",
                        'account_id': account_id,
                        'price_unit': line.price_unit,
                        'quantity': line.rental_duration,
                        'rental_line_ids': [(6, 0, [line.id])],
                        'product_uom_id': line.product_id.uom_id.id,
                        'product_id': line.product_id.id,
                        'tax_ids': [(6, 0, line.tax_id.ids)],
                    }))
                # delay_duration_dict = self._compute_duration_vals(rental.end_date,
                #                                                   datetime.datetime.today().date())
                # delay_duration_days = delay_duration_dict['day']
                # if rental.extended_period > 0:
                #     initial_end_date = rental.end_date - relativedelta(days=rental.extended_period)
                #     # initial_period = self._compute_duration_vals(rental.start_date, initial_end_date)
                #     # period = rental.extended_period + initial_period['days']
                #     inv_name += "EX"
                #     start_date = initial_end_date + relativedelta(days=1)
                #     end_date = datetime.datetime.today().date()
                #     extended_period = rental.extended_period
                #     if delay_duration_days >= 1:
                #         extended_period = rental.extended_period + delay_duration_days
                #     inv_line.append((0, 0, {
                #         'name': line.product_id.description_rental or line.name or " ",
                #         'account_id': account_id,
                #         'price_unit': line.product_id.rent_per_day,
                #         'quantity': extended_period,
                #         'rental_line_ids': [(6, 0, [line.id])],
                #         'product_uom_id': line.product_id.uom_id.id,
                #         'product_id': line.product_id.id,
                #         'tax_ids': [(6, 0, line.tax_id.ids)],
                #     }))
                #
                # else:
                #     if rental.rental_initial == duration:
                #         inv_line.append((0, 0, {
                #             'name': line.product_id.description_rental or line.name or " ",
                #             'account_id': account_id,
                #             'price_unit': line.price_unit,
                #             'quantity': line.rental_duration,
                #             'rental_line_ids': [(6, 0, [line.id])],
                #             'product_uom_id': line.product_id.uom_id.id,
                #             'product_id': line.product_id.id,
                #             'tax_ids': [(6, 0, line.tax_id.ids)],
                #         }))
                #     elif rental.rental_initial < duration:
                #         duration = rental.rental_initial
                #         if rental.state != 'draft':
                #             end_date = datetime.datetime.today().date()
                #             inv_name += "EX"
                #             duration = duration - rental.rental_initial
                #         inv_line.append((0, 0, {
                #             'name': line.product_id.description_rental or inv_name or " ",
                #             'account_id': account_id,
                #             'price_unit': line.price_unit,
                #             'quantity': duration,
                #             'rental_line_ids': [(6, 0, [line.id])],
                #             'product_uom_id': line.product_id.uom_id.id,
                #             'product_id': line.product_id.id,
                #             'tax_ids': [(6, 0, line.tax_id.ids)],
                #         }))
            if rental.check_saleable:
                for line in rental.sale_line:
                    account_id = False
                    if line.product_id.id:
                        account_id = line.product_id.categ_id.property_account_income_categ_id.id
                    if not account_id:
                        raise UserError(
                            _(
                                'There is no income account defined for this product: "%s". You may have to install a chart of account from Accounting app, settings menu.') % \
                            (line.product_id.name,))
                    name = _('Down Payment')

            invoice = inv_obj.create({
                'name': rental.client_order_ref or inv_name or " ",
                'invoice_origin': rental.name or " ",
                'move_type': 'out_invoice',
                'rental_id': rental.id,
                'ref': False,
                'partner_id': rental.partner_invoice_id.id,
                'invoice_line_ids': inv_line,
                'currency_id': rental.pricelist_id.currency_id.id,
                'user_id': rental.user_id.id,
                'rental_start_date': start_date,
                'rental_end_date': end_date,
                'from_rent_order': True,
            })
        return invoice

    def _create_invoice(self, force=False):
        inv_obj = self.env['account.move']
        inv_line = []
        for rental in self:
            for line in rental.rental_line:
                account_id = False
                if line.product_id.id:
                    account_id = line.product_id.categ_id.property_account_income_categ_id.id
                if not account_id:
                    raise UserError(
                        _(
                            'There is no income account defined for this product: "%s". You may have to install a chart of account from Accounting app, settings menu.') % \
                        (line.product_id.name,))
                if rental.extended_period > 0:
                    inv_line.append((0, 0, {
                        'name': line.product_id.description_rental or line.name or " ",
                        'account_id': account_id,
                        'price_unit': line.product_id.rent_per_day,
                        'quantity': rental.extended_period,
                        'rental_line_ids': [(6, 0, [line.id])],
                        'product_uom_id': line.product_id.uom_id.id,
                        'product_id': line.product_id.id,
                        'tax_ids': [(6, 0, line.tax_id.ids)],
                    }))

                else:
                    duration_dict = self._compute_duration_vals(rental.start_date, rental.end_date)
                    duration = 0
                    if rental.rental_initial_type == 'days':
                        duration = duration_dict['day']
                    elif rental.rental_initial_type == 'weeks':
                        duration = duration_dict['week']
                    elif rental.rental_initial_type == 'months':
                        duration = duration_dict['month']
                    if rental.rental_initial == duration:
                        inv_line.append((0, 0, {
                            'name': line.product_id.description_rental or line.name or " ",
                            'account_id': account_id,
                            'price_unit': line.price_unit,
                            'quantity': line.rental_duration,
                            'rental_line_ids': [(6, 0, [line.id])],
                            'product_uom_id': line.product_id.uom_id.id,
                            'product_id': line.product_id.id,
                            'tax_ids': [(6, 0, line.tax_id.ids)],
                        }))
                    else:
                        inv_line.append((0, 0, {
                            'name': line.product_id.description_rental or line.name or " ",
                            'account_id': account_id,
                            'price_unit': line.price_unit,
                            'quantity': duration,
                            'rental_line_ids': [(6, 0, [line.id])],
                            'product_uom_id': line.product_id.uom_id.id,
                            'product_id': line.product_id.id,
                            'tax_ids': [(6, 0, line.tax_id.ids)],
                        }))
            invoice = inv_obj.create({
                'name': rental.client_order_ref or rental.name or " ",
                'type': 'out_invoice',
                'rental_id': rental.id,
                'ref': False,
                'partner_id': rental.partner_invoice_id.id,
                'invoice_line_ids': inv_line,
                'currency_id': rental.pricelist_id.currency_id.id,
                'user_id': rental.user_id.id,
                'rental_start_date': rental.start_date,
                'rental_end_date': rental.end_date,
                'from_rent_order': True,
            })
        return invoice

    def action_button_vehicle_checking(self):
        picking_rental_obj = self.env['stock.picking'].search([('origin', '=', self.name)])
        picking_rental_return_obj = self.env['stock.return.picking']
        picking_return_line_obj = self.env['stock.return.picking.line']
        picking_checklist_obj = self.env['rental.checklist']
        rol_active = self.env['rental.order.line'].search([('rental_id', '=', self.id)])
        return_rent = False
        for rental in self:
            for picking in picking_rental_obj:
                # picking_done = pytz.utc.localize(picking.date_done).astimezone()
                # picking_done = picking_done.replace(tzinfo=None)
                duration_dict = self._compute_duration_vals(picking.date_done, fields.datetime.now())
            duration = 0
            if rental.rental_initial_type == 'days':
                duration = duration_dict['day']
            elif rental.rental_initial_type == 'weeks':
                duration = duration_dict['week']
            elif rental.rental_initial_type == 'months':
                duration = duration_dict['month']
            if rental.rental_initial < duration or rental.extended_period > 0:
                self._create_invoice_with_saleable()
            else:
                rental.update({'days_duration': rental.rental_initial})

        for clrp in picking_rental_obj:
            picking_checklist = picking_checklist_obj.search([('checklist_number', '=', clrp.id)])
            for mvv in clrp.move_lines:
                for mvv_lns in mvv.move_line_ids:
                    for x in rol_active:
                        if mvv_lns.lot_id.id == x.lot_id.id:
                            if clrp.state == 'done':
                                return_rent = picking_rental_return_obj.create(
                                    {'picking_id': clrp.id, 'location_id': clrp.location_id.id})
                            else:
                                raise UserError(
                                    _('You can only close rental while the replaced products are delivered!'))

        for clrp1 in picking_rental_obj:
            for mv in clrp1.move_lines:
                for mv_lns in mv.move_line_ids:
                    for x1 in rol_active:
                        if mv_lns.lot_id.id == x1.lot_id.id:
                            return_line = picking_return_line_obj.create(
                                {'product_id': mv.product_id.id, 'quantity': 1, 'wizard_id': return_rent.id,
                                 'move_id': mv.id})

        if return_rent:
            ret = return_rent.create_returns()
        ret_move_obj = self.env['stock.move'].search([('picking_id', '=', ret['res_id'])])
        for clrp2 in picking_rental_obj:
            ori_move_obj = self.env['stock.move'].search([('picking_id', '=', clrp2.id)])
            for mv in clrp2.move_lines:
                for mv_lns in mv.move_line_ids:
                    for x1 in rol_active:
                        if mv_lns.lot_id.id == x1.lot_id.id:
                            for mv_l in ori_move_obj:
                                if mv_lns.lot_id.id == x1.lot_id.id:
                                    for mv_line in mv_l.move_line_ids:
                                        if mv_lns.lot_id.id == x1.lot_id.id:
                                            for rt1 in ret_move_obj:
                                                if picking_checklist:
                                                    for pcl in picking_checklist:
                                                        picking_checklist_obj.create(
                                                            {'name': pcl.name.id,
                                                             'checklist_active': pcl.checklist_active,
                                                             'checklist_number': rt1.picking_id.id,
                                                             'price': pcl.price})
                                                rt1.picking_id.car_checked = False
                                                if mv_lns.lot_id.product_id.id == x1.lot_id.product_id.id:
                                                    for mvline in rt1.move_line_ids:
                                                        if mvline.product_id.id == mv_line.product_id.id:
                                                            if mv_line.lot_id.id == x1.lot_id.id:
                                                                mvline.update({'lot_id': mv_line.lot_id.id,
                                                                               'qty_done': mv_line.qty_done})

        for rental in self:
            rental.update({'state': 'checking'})

    def action_button_close_rental(self):

        invoices = self.env['account.move'].search([('invoice_origin', '=', self.name)])
        print("self.name", self.name)
        f = 0
        for invoice in invoices:
            if invoice.payment_state != 'paid':
                f = 1
                break
        if f == 0:
            self.state = 'close'
            for rent in self:
                for rl in rent.rental_line:
                    lot_id = rl.lot_id
                    rh_ids = self.env['rental.history'].search(
                        [('production_lot_id_custom', '=', lot_id.id), ('rental_id', '=', rl.rental_id.id)])
                    for rh in rh_ids:
                        rh.state = 'close'
        else:
            raise UserError("Some Invoices are pending")


class RentalOrderLine(models.Model):
    _inherit = 'rental.order.line'
    price_unit = fields.Float('Price Unit', readonly=True, required=True, digits='Product Price', default=0.0)
    rental_duration = fields.Integer(related="rental_id.rental_initial", string='Initial Terms')

    @api.model
    def create(self, values):
        price_unit = 0.0
        if any(f not in values for f in ['product_categ_id', 'product_id', 'price_unit']):
            lot = self.env['stock.production.lot'].browse(values.get('lot_id'))
            rental = self.env['rental.order'].browse(values.get('rental_id'))
            if rental.rental_initial_type:
                if rental.rental_initial_type == 'days':
                    price_unit = lot.product_id.rent_per_day
                elif rental.rental_initial_type == 'weeks':
                    price_unit = lot.product_id.rent_per_week
                elif rental.rental_initial_type == 'months':
                    price_unit = lot.product_id.rent_per_month
            values['product_categ_id'] = values.setdefault('product_categ_id', lot.product_id.categ_id.id)
            values['product_id'] = values.setdefault('product_id', lot.product_id.id)
            values['price_unit'] = values.setdefault('price_unit', price_unit)

        line = super(RentalOrderLine, self).create(values)
        return line

    @api.onchange('lot_id')
    def lot_id_change(self):
        if not self.rental_id.rental_initial or self.rental_id.rental_initial <= 0:
            raise UserError(_('Initial Terms can not set to Zero'))
        vals = {}
        price_unit = 0.0
        if not self.lot_id:
            return self.update(vals)

        product = self.lot_id.product_id
        name = product.name_get()[0][1]
        if product.description_rental:
            name += '\n' + product.description_rental
        vals['name'] = name
        rental_initial_type = self.rental_id.rental_initial_type
        if rental_initial_type:
            if rental_initial_type == 'days':
                price_unit = product.rent_per_day
            elif rental_initial_type == 'weeks':
                price_unit = product.rent_per_week
            elif rental_initial_type == 'months':
                price_unit = product.rent_per_month
        vals.update({'product_id': product or False,
                     'product_categ_id': product.categ_id or False,
                     'price_unit': price_unit,
                     })
        return self.update(vals)

    @api.depends('price_unit', 'tax_id')
    def _compute_amount(self):
        """
        Compute the amounts of the SO line.
        """
        for line in self:
            taxes = line.tax_id.compute_all(line.price_unit, None, self.rental_duration)
            line.update({
                'price_tax': sum(t.get('amount', 0.0) for t in taxes.get('taxes', [])),
                'price_total': taxes['total_included'],
                'price_subtotal': taxes['total_excluded'],
            })


class RentalChecklist(models.Model):
    _name = 'rental.checklist'

    name = fields.Many2one('car.tools', string="Name")
    checklist_active = fields.Boolean(string="Available", default=True)
    checklist_number = fields.Many2one('stock.picking', string="Checklist Number")
    price = fields.Float(string="Price")

    @api.onchange('name')
    def onchange_name(self):
        self.price = self.name.price


class Picking(models.Model):
    _inherit = "stock.picking"

    checklist_line = fields.One2many('rental.checklist', 'checklist_number', string="Checklist",
                                     states={'done': [('readonly', True)]})
    attachment_ids = fields.Many2many('ir.attachment', 'rent_checklist_ir_attachments_rel',
                                      'rental_id', 'attachment_id', string="Attachments",
                                      help="Images of the vehicle before contract/any attachments")
    car_checked = fields.Boolean(string="Car Checked", default=False, track_visibility='onchange')

    def action_verify(self):
        self.car_checked = True

    def button_validate(self):
        # Clean-up the context key at validation to avoid forcing the creation of immediate
        # transfers.
        if self.for_rental_move:
            if not self.car_checked:
                raise UserError(_('Please verify the car checklist !!!'))
            for move in self.move_ids_without_package:
                if move.new_odometer < move.odometer:
                    raise UserError(_('Please update the vehicle Odometer !!!'))
                elif move.new_odometer > move.odometer:
                    if move.product_id.fleet_id:
                        self.env['fleet.vehicle.odometer'].create({
                            'value': move.new_odometer,
                            'date': datetime.datetime.today(),
                            'vehicle_id': move.product_id.fleet_id.id
                        })
                        if move.picking_code == 'incoming':
                            if self.group_id.rental_id:
                                for rental in self.group_id.rental_id:
                                    duration = rental.days_duration
                                    km_allowed = move.product_id.km_allowed
                                    total_km_allowed = duration * km_allowed
                                    km_diff = move.new_odometer - move.odometer
                                    if km_diff > total_km_allowed:
                                        km_inv = km_diff - total_km_allowed
                                        rental.update({'km_diff': km_inv})
                                        extra_km_product = self.env['product.product'].search(
                                            [('name', '=', 'Extra KM')])
                                        if extra_km_product:
                                            rental._create_km_invoice(extra_km_product)

                else:
                    if move.picking_code == 'incoming':
                        raise UserError(_('Please update the vehicle Odometer !!!'))

        ctx = dict(self.env.context)
        ctx.pop('default_immediate_transfer', None)
        self = self.with_context(ctx)

        # Sanity checks.
        pickings_without_moves = self.browse()
        pickings_without_quantities = self.browse()
        pickings_without_lots = self.browse()
        products_without_lots = self.env['product.product']
        for picking in self:
            if not picking.move_lines and not picking.move_line_ids:
                pickings_without_moves |= picking

            picking.message_subscribe([self.env.user.partner_id.id])
            picking_type = picking.picking_type_id
            precision_digits = self.env['decimal.precision'].precision_get('Product Unit of Measure')
            no_quantities_done = all(
                float_is_zero(move_line.qty_done, precision_digits=precision_digits) for move_line in
                picking.move_line_ids.filtered(lambda m: m.state not in ('done', 'cancel')))
            no_reserved_quantities = all(
                float_is_zero(move_line.product_qty, precision_rounding=move_line.product_uom_id.rounding) for move_line
                in picking.move_line_ids)
            if no_reserved_quantities and no_quantities_done:
                pickings_without_quantities |= picking

            if picking_type.use_create_lots or picking_type.use_existing_lots:
                lines_to_check = picking.move_line_ids
                if not no_quantities_done:
                    lines_to_check = lines_to_check.filtered(
                        lambda line: float_compare(line.qty_done, 0, precision_rounding=line.product_uom_id.rounding))
                for line in lines_to_check:
                    product = line.product_id
                    if product and product.tracking != 'none':
                        if not line.lot_name and not line.lot_id:
                            pickings_without_lots |= picking
                            products_without_lots |= product

        if not self._should_show_transfers():
            if pickings_without_moves:
                raise UserError(_('Please add some items to move.'))
            if pickings_without_quantities:
                raise UserError(self._get_without_quantities_error_message())
            if pickings_without_lots:
                raise UserError(_('You need to supply a Lot/Serial number for products %s.') % ', '.join(
                    products_without_lots.mapped('display_name')))
        else:
            message = ""
            if pickings_without_moves:
                message += _('Transfers %s: Please add some items to move.') % ', '.join(
                    pickings_without_moves.mapped('name'))
            if pickings_without_quantities:
                message += _(
                    '\n\nTransfers %s: You cannot validate these transfers if no quantities are reserved nor done. To force these transfers, switch in edit more and encode the done quantities.') % ', '.join(
                    pickings_without_quantities.mapped('name'))
            if pickings_without_lots:
                message += _('\n\nTransfers %s: You need to supply a Lot/Serial number for products %s.') % (
                    ', '.join(pickings_without_lots.mapped('name')),
                    ', '.join(products_without_lots.mapped('display_name')))
            if message:
                raise UserError(message.lstrip())

        # Run the pre-validation wizards. Processing a pre-validation wizard should work on the
        # moves and/or the context and never call `_action_done`.
        if not self.env.context.get('button_validate_picking_ids'):
            self = self.with_context(button_validate_picking_ids=self.ids)
        res = self._pre_action_done_hook()
        if res is not True:
            return res

        # Call `_action_done`.
        if self.env.context.get('picking_ids_not_to_backorder'):
            pickings_not_to_backorder = self.browse(self.env.context['picking_ids_not_to_backorder'])
            pickings_to_backorder = self - pickings_not_to_backorder
        else:
            pickings_not_to_backorder = self.env['stock.picking']
            pickings_to_backorder = self
        pickings_not_to_backorder.with_context(cancel_backorder=True)._action_done()
        pickings_to_backorder.with_context(cancel_backorder=False)._action_done()
        if self.group_id:
            group_id = self.group_id
            if group_id.rental_id:
                rental_id = group_id.rental_id
                if self.picking_type_code:
                    picking_type = self.picking_type_code
                    if picking_type == 'outgoing':
                        for rental in rental_id:
                            rental.outgoing_done = True
                    elif picking_type == 'incoming':
                        for rental in rental_id:
                            rental.incoming_done = True

        return True


class CarTools(models.Model):
    _name = 'car.tools'

    name = fields.Char(string="Name")
    price = fields.Float(string="Price")


class StockMove(models.Model):
    _inherit = "stock.move"

    odometer = fields.Float(related="product_id.odometer", string='Last Odometer',
                            help='Odometer measure of the vehicle at the moment of this log')
    new_odometer = fields.Float(string='Current Odometer')
    rent_ok = fields.Boolean(related="product_id.rent_ok", string='Can be Rented')

class RentalProductReplace(models.Model):
    _inherit = "rental.product.replace"

    def replace_product(self):

        rental_id = self._context.get('active_id')
        rental = self.env['rental.order'].browse(rental_id)
        replace_lines = []
        is_replace = []
        move_lines = []
        pick_ids = self.env['stock.picking'].search(
            [('group_id', '=', rental.procurement_group.id), ('for_rental_move', '=', True)])

        if not self.replace_product_ids:
            raise UserError(_('Select atleast one product to Replace!'))

        for line in self.replace_product_ids:
            for product in rental.rental_line:
                if product.product_id.id == line.product_id.id and product.lot_id.id == line.lot_id.id:
                    raise UserError(_('You Can Not Replace Product With Same Lot Number!'))

        for pick in pick_ids:
            if pick.state != 'done':
                raise UserError(_('You can only replace products those are delivered!'))

        for rl in self.existing_product_ids:
            lot_id = rl.ro_line_id.lot_id
            rh_ids = self.env['rental.history'].search(
                [('production_lot_id_custom', '=', lot_id.id), ('rental_id', '=', rental.id)])
            for rh in rh_ids:
                rh.state = 'close'

        for line in self.existing_product_ids:
            if line.replace_item == True and line.ro_line_id:
                flag = True
                for line2 in self.replace_product_ids:
                    if line.ro_line_id.product_id.id != line2.product_id.id:
                        raise UserError(_('You have to select Same Product!'))

        for line in self.existing_product_ids:
            if line.replace_item == True and line.ro_line_id:
                is_replace.append(line.id)
                line.ro_line_id.unlink()

        if len(is_replace) == 0:
            raise UserError(_('Select atleast one product to Replace!'))
        else:
            pick_ids.action_cancel()

        move_lines2 = []
        for rline in self.replace_product_ids:
            rline.product_id.replacement_value = rline.unit_price
            product = rline.product_id
            name = product.name_get()[0][1]
            pick_type = self.env['stock.picking.type'].search(
                [('name', '=', _('Delivery Orders')), ('warehouse_id', '=', rental.warehouse_id.id)]).id
            if product.description_sale:
                name += '\n' + product.description_sale

            vals = {'name': name,
                    'product_categ_id': rline.product_id.categ_id.id,
                    'product_id': rline.product_id.id,
                    'price_unit': rline.unit_price,
                    'lot_id': rline.lot_id.id,
                    'rental_id': rental_id}
            replace_lines.append(self.env['rental.order.line'].create(vals).id)
            self.env['rental.history'].create({
                'production_lot_id_custom': vals['lot_id'],
                'start_date': rental.start_date,
                'end_date': rental.end_date,
                'rental_id': vals['rental_id'],
                'state': 'confirm'
            })

        if replace_lines:
            for i in self.env['rental.order.line'].browse(replace_lines):
                i._action_launch_procurement_rule_custom()  # picking is creating from this
        return
