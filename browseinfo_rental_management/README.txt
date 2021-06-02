
Date 10-02-2020
version : 13.0.0.0
---> migrate browseinfo_rental_management in v13


version : 13.0.0.1
===> change src location in picking of saleable product

version : 13.0.0.2

1) Add hourly and weekly selection for bill frequency.
2) Add constraint for start date and end date.
3) Add constraint for hourly initial and bill frequency terms.
4) add invoice counter for hourly invoice configuration.
5) Update invoice cron to hourly bases. and Update
renew date conditions based on bill frequency.
6) Solve issue of singleton error while order confirm.
7) Update security.
8) Solve duplicate order issue.

Version 13.0.0.3 : (29/04/20)
		- Change string 'Monthly rent' to 'Rent' in rental line.
		- Remove required true from py for start & end date.
		- Add condition not to create picking of service product (in saleable products) 

Version 13.0.0.4 : (30/07/20)
		- Solve issue of create picking of saleable products with non admin user.

Version 13.0.0.5: (16/12/20)
		- Fixed issue of total amount not getting changed in sale order after changing saleable products. 		
