# Copyright (c) 2022, libracore and contributors
# For license information, please see license.txt
#
# This is the main EDI interaction file
#

from datetime import datetime
import frappe
import hashlib
from frappe.utils import cint

"""
Creates a new EDI File of PRICAT type
"""
def create_pricat(edi_connection):
    edi_con = frappe.get_doc("EDI Connection", edi_connection)
    edi_file = frappe.get_doc({
        'doctype': 'EDI File',
        'edi_connection': edi_connection,
        'edi_type': edi_con.edi_type,
        'date': datetime.now(),
        'title': "PRICAT - {0}".format(datetime.now())
    })
    edi_file.insert()
    frappe.db.commit()
    return edi_file.name
    
"""
Prepares the content of a PRICAT file for download
"""
def download_pricat(edi_file):
    edi = frappe.get_doc("EDI File", edi_file)
    edi_con = frappe.get_doc("EDI Connection", edi.edi_connection)
    price_list = frappe.get_doc("Price List", edi_con.price_list)
    
    content_segments = []
    # envelope
    content_segments.append("UNB+{charset}:3+{gln_sender}:14+{gln_recipient}:14+{yy:02d}{mm:02d}{dd:02d}:{HH:02d}{MM:02d}+{name}+++++EANCOMREF 52+{test}'".format(
        charset=edi_con.charset,
        gln_sender=edi_con.gln_sender or "",
        gln_recipient=edi_con.gln_recipient or "",
        yy=int(str(edi.date.year)[2:4]),
        mm=edi.date.month,
        dd=edi.date.day,
        HH=edi.date.hour,
        MM=edi.date.minute,
        name=edi.name,
        test=cint(edi.test)
    ))
    # message header
    content_segments.append("UNH+{name}+PRICAT:D:01B:UN:EAN008'".format(
        name=edi.name
    ))
    # beginning: price/sales catalogue number (hashed price list name, max. length 17)
    content_segments.append("BGM+9+{price_list}+9'".format(
        price_list=hashlib.md5((edi_con.price_list or "notdefined").encode('utf-8')).hexdigest()[:17]
    ))
    # ### SG1
    # message date
    content_segments.append("DTM+137:{year:04d}{month:02d}{day:02d}:102'".format(
        year=edi.date.year, month=edi.date.month, day=edi.date.day
    ))
    ## date range placeholders
    content_segments.append("DTM+194:20000101:102'")
    content_segments.append("DTM+206:20991231:102'")
    
    # ### SG2
    # Reference
    content_segments.append("RFF+VA:{tax_id}'".format(
        tax_id=(frappe.get_value("Company", edi_con.company, "tax_id") or "").replace("-", "").replace(".", "")
    ))
    
    # buyer location number
    content_segments.append("NAD+BY+{gln_recipient}::9'".format(
        gln_recipient=edi_con.gln_recipient or ""
    ))

    # supplier location number
    content_segments.append("NAD+BY+{gln_sender}::9'".format(
        gln_sender=edi_con.gln_sender or ""
    ))
    
    # ### SG6
    # currency
    content_segments.append("CUX+2:{currency}:8'".format(
        currency=price_list.currency
    ))
    
    # ##### Price/Catalogue Detail Section
    # ### SG17
    
    # Product group information
    content_segments.append("PGI+3'")
    
    # ### SG36
    for item in edi.pricat_items:
        item_doc = frappe.get_doc("Item", item.item_code)
        # line item
        content_segments.append("LIN+{idx}+{action}+{gtin}:SRV'".format(
            idx=item.idx,
            action=item.action.split("=")[0],
            gtin=item.gtin
        ))
        # internal item code
        content_segments.append("PIA+1+{item_code}'".format(
            item_code=item.item_code[:35]
        ))
        content_segments.append("PIA+5+{gtin}:SA'".format(
            gtin=item.gtin
        ))
        # description
        content_segments.append("IMD+F+ANM+:::{item_name}:'".format(
            item_name=item.item_name
        ))
        # fabric (132, formerly U01)
        content_segments.append("IMD+F+132+:::{fabric}:'".format(
            fabric=item_doc.get("fabric") or ""
        ))
        # brand
        content_segments.append("IMD+F+BRN+:::{brand}:'".format(
            brand=item_doc.get("brand") or ""
        ))
        # colour
        for attr in item_doc.attributes:
            if attr.attribute in ["Colour", "Color", "Farbe"]:
                content_segments.append("IMD+F+35+:::{colour}:'".format(
                    colour=attr.attribute_value or ""
                ))
        # quantity: minimum order
        content_segments.append("QTY+53:{min_qty}:{uom}'".format(
            min_qty=item.min_qty,
            uom=get_uom_code(item_doc.get("stock_uom") or "PCE")
        ))
        # quantity: qty per pack
        content_segments.append("QTY+53:{min_qty}:{uom}'".format(
            min_qty=item.qty_per_pack,
            uom=get_uom_code(item_doc.get("stock_uom") or "PCE")
        ))
        # availability date
        content_segments.append("DTM+44:20000101:102'")
        
        # price
        content_segments.append("PRI+AAA:{rate}:CA'".format(
            rate=item.rate
        ))
        
        # currency
        content_segments.append("CUX+2:{currency}:8'".format(
            currency=price_list.currency
        ))
    # closing segment
    content_segments.append("UNT+{segment_count}+{name}'".format(
        segment_count=len(content_segments) + 1,
        name=edi.name
    ))
    content_segments.append("UNZ+{message_count}+{name}'".format(
        message_count=1,
        name=edi.name
    ))
    content = "\n".join(content_segments)
    return content

def get_uom_code(uom):
    if uom.lower() == "pair":
        return "PR"
    elif uom.lower() == "nos":
        return "PCE"
        
    else:
        # fallback to piece
        return "PCE"
