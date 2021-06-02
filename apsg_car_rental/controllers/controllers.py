# -*- coding: utf-8 -*-
# from odoo import http


# class ApsgCarRental(http.Controller):
#     @http.route('/apsg_car_rental/apsg_car_rental/', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/apsg_car_rental/apsg_car_rental/objects/', auth='public')
#     def list(self, **kw):
#         return http.request.render('apsg_car_rental.listing', {
#             'root': '/apsg_car_rental/apsg_car_rental',
#             'objects': http.request.env['apsg_car_rental.apsg_car_rental'].search([]),
#         })

#     @http.route('/apsg_car_rental/apsg_car_rental/objects/<model("apsg_car_rental.apsg_car_rental"):obj>/', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('apsg_car_rental.object', {
#             'object': obj
#         })
