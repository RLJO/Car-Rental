from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.osv import expression
from hijri_converter import convert
from datetime import datetime

class AccountAssetAsset(models.Model):
    _inherit = 'account.asset'

    name = fields.Char(string='Asset Name', required=True, readonly=True, states={'draft': [('readonly', False)]})
    vehicle_id = fields.Many2one('fleet.vehicle', string='Vehicle',  change_default=True, readonly=True, states={'draft': [('readonly', False)]})
    code = fields.Char(related='vehicle_id.code', string='Reference', size=32, required=True, readonly=True, states={'draft': [('readonly', False)]})
    is_vehicle = fields.Boolean(default=True, readonly=True, string='Add to fleet', states={'draft': [('readonly', False)]})
    account_analytic_id = fields.Many2one('account.analytic.account', related='vehicle_id.account_analytic_id', string='Analytic Account',
                                          domain="[('is_vehicle', '=', True)]")


class FleetVehicle(models.Model):
    _inherit = 'fleet.vehicle'

    code = fields.Char(string='Reference Number', required=True, size=32)
    license_plate = fields.Char(track_visibility="onchange",
                                help='License plate number of the vehicle (i = plate number for a car)', required=True)
    color = fields.Char('Major Color')
    minor_color = fields.Char('Minor Color')
    vehicle_work = fields.Boolean('Vehicle Work', default=True, track_visibility="onchange")
    account_analytic_id = fields.Many2one('account.analytic.account', string='Analytic Account')
    hours = fields.Float(compute='_get_hours', inverse='_set_odometer', string='Last Hours',
                            help='Hours measure of the vehicle at the moment of this log')
    mvpi_state = fields.Selection([('dne', 'Does not exist'), ('expired', 'Expired'), ('valid', 'Valid')], 'MVPI State',
                                  default="dne")
    insurance_state = fields.Selection([('dne', 'Does not exist'), ('expired', 'Expired'), ('valid', 'Valid')],
                                       'Insurance State', default="dne")
    ownership_date_h = fields.Char('Hijri Ownership Date')
    ownership_date = fields.Date('Ownership Date', readonly=True, compute='_compute_ownership_date')
    owner_id = fields.Char('Owner ID')
    owner_name = fields.Char('Owner Name')
    license_expiry_date_h = fields.Char('Hijri License Expiry Date')
    license_expiry_date = fields.Date('License Expiry Date', readonly=True, compute='_compute_license_expiry_date')
    plate_type = fields.Selection([
        ('pcbus', 'Public Bus'),
        ('pvbus', 'Private Bus'),
        ('pvcar', 'Private Car'),
        ('pctransport', 'Public Transport'),
        ('pvtransport', 'Private Transport'),
        ('equipment', 'Equipment'),
        ('motorcycle', 'Motorcycle'), ], 'Plate Type', required=True)



    def name_get(self):
        result = []
        for vehicle in self:
            name = '[' + vehicle.code + '] ' + ' ' + vehicle.name
            result.append((vehicle.id, name))
        return result

    @api.depends('license_expiry_date_h')
    def _compute_license_expiry_date(self):
        license_expiry_date = self.convert_date(self.license_expiry_date_h)
        if license_expiry_date is not None:
            if len(license_expiry_date) == 1:
                raise UserError(_('Enter the correct (License Expiry Date)'))
            else:
                self.license_expiry_date = license_expiry_date[0]
        else:
            self.license_expiry_date = None

    @api.depends('ownership_date_h')
    def _compute_ownership_date(self):
        ownership_date = self.convert_date(self.ownership_date_h)
        if ownership_date is not None:
            if len(ownership_date) == 1:
                raise UserError(_('Enter the correct (Ownership Date)'))
            else:
                self.ownership_date = ownership_date[0]
        else:
            self.ownership_date = None

    def convert_date(self, date):
        if date:
            d = date.split('/')
            if len(d) == 3:
                try:
                    day = int(d[0])
                    month = int(d[1])
                    year = int(d[2])
                    g = convert.Hijri(year, month, day).to_gregorian()
                    error = False
                    return g, error
                except:
                    error = True
                    return error,
            else:
                error = True
                return error,


    def _get_hours(self):
        FleetVehicalHours = self.env['fleet.vehicle.odometer']
        for record in self:
            vehicle_hours = FleetVehicalHours.search([('vehicle_id', '=', record.id), ('hours', '!=', False)], order='hours desc', limit=1)
            if vehicle_hours:
                record.hours = vehicle_hours.hours
            else:
                record.hours = 0

    def _set_odometer(self):
        for record in self:
            if record.odometer:
                date = fields.Date.context_today(record)
                if record.hours:
                    data = {'value': record.odometer, 'date': date, 'vehicle_id': record.id, 'hours': record.hours}
                else:
                    data = {'value': record.odometer, 'date': date, 'vehicle_id': record.id}
                self.env['fleet.vehicle.odometer'].create(data)
            elif record.hours:
                data = {'date': date, 'vehicle_id': record.id, 'hours': record.hours}
                self.env['fleet.vehicle.odometer'].create(data)

    def toggle_stop(self):
        for vals in self:
            if vals['vehicle_work']:
                vals['vehicle_work'] = False
            else:
                vals['vehicle_work'] = True
        self.write({'vehicle_work': vals['vehicle_work']})
        return True

    @api.model
    def create(self, vals):
        if 'ownership_date_h' in vals and vals['ownership_date_h']:
            self.convert_date(vals['ownership_date_h'])
        if self.env['fleet.vehicle'].search([('code', '=', vals['code'])]):
            raise UserError(_('Vehicle Reference number already exists'))
        else:
            res = super(FleetVehicle, self).create(vals)
        #code = {
            #'name': vals['code'],
            #'license_plate': vals['license_plate'],
            #'model_id': vals['model_id'],
            #'vehicle_id': res.id
        #}
        #self.env['fleet.vehicle.code'].create(code)
        if 'driver_id' in vals and vals['driver_id']:
            res.create_driver_history(vals['driver_id'])
        return res

    def write(self, vals):
        #vehicle = self.env['fleet.vehicle'].search([('id', '=', self.id)])

        #if 'code' in vals and vals['code']:
           # vcode = vals['code']
        #else:
            #vcode = vehicle['code']

        #if 'license_plate' in vals and vals['license_plate']:
            #vlicense = vals['license_plate']
        #else:
            #vlicense = vehicle['license_plate']

        #if 'model_id' in vals and vals['model_id']:
            #vmodel = vals['model_id']
        #else:
            #vmodel = self.model_id.id

        #code = {
            #'name': vcode,
            #'license_plate': vlicense,
            #'model_id': vmodel

        #}
        #code_id = {
            #'name': vcode,
            #'license_plate': vlicense,
            #'model_id': vmodel,
            #'vehicle_id': self.id
        #}
        if 'code' in vals and vals['code']:
            if self.env['fleet.vehicle'].search([('code', '=', vals['code'])]):
                raise UserError(_('Vehicle Reference number already exists'))
        res = super(FleetVehicle, self).write(vals)
        #if self.env['fleet.vehicle.code'].search([('vehicle_id', '=', self.id)]):
            #self.env['fleet.vehicle.code'].search([('vehicle_id', '=', self.id)]).write(code)
        #else:
            #self.env['fleet.vehicle.code'].create(code_id)
        if 'driver_id' in vals and vals['driver_id']:
            self.create_driver_history(vals['driver_id'])
        if 'active' in vals and not vals['active']:
            self.mapped('log_contracts').write({'active': False})
        return res

    @api.model
    def _name_search(self, name, args=None, operator='ilike', limit=100, name_get_uid=None):
        domain = args or []
        domain = expression.AND([domain, ['|', ('name', operator, name), ('code', operator, name)]])
        rec = self._search(domain, limit=limit, access_rights_uid=name_get_uid)
        return self.browse(rec).name_get()


class FleetVehicleOdometer(models.Model):
    _inherit = ['fleet.vehicle.odometer']

    hours = fields.Float('Hours Value', group_operator="max")

#class FleetVehicleCode(models.Model):
    #_name = 'fleet.vehicle.code'
    #_order = "id desc"
    #name = fields.Char()
    #license_plate = fields.Char()
    #model_id = fields.Many2one('fleet.vehicle.model', 'Model',
                                #required=True, help='Model of the vehicle')
    #vehicle_id = fields.Integer('vehicle')
