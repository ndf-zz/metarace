
import os
import cairo
import gi
gi.require_version('Pango', '1.0')
from gi.repository import Pango 
gi.require_version('PangoCairo', '1.0')
from gi.repository import PangoCairo
gi.require_version('Rsvg', '2.0')
from gi.repository import Rsvg
import datetime
import math
import json
import time
import random
import csv
import metarace
from metarace import tod
from metarace import htlib
from metarace import jsonconfig

# JSON report API version
APIVERSION = '1.0.3'

# xls cell styles
#XS_LEFT = xlwt.easyxf()
#XS_RIGHT = xlwt.easyxf('align: horiz right')
#XS_TITLE = xlwt.easyxf('font: bold on')
#XS_SUBTITLE = xlwt.easyxf('font: italic on')
#XS_MONOSPACE = xlwt.easyxf('font: name Courier')

# Meta cell icon classes
ICONMAP = {'datestr':'glyphicon glyphicon-search',
           'docstr':'glyphicon glyphicon-flag',
           'diststr':'glyphicon glyphicon-road', 
           'commstr':'glyphicon glyphicon-user',
           'orgstr':'glyphicon glyphicon-star',
           'download':'glyphicon glyphicon-file',
           'default':'glyphicon glyphicon-file'}

# "download as" file types
FILETYPES = {'txt':'Blog Text',
             'pdf':'PDF',
             'xls':'Spreadsheet',
             'json':'JSON'}

# CSV Report Builder constants
CSV_REPORT_COLUMNS = {
	'type':	'Type',
	'head':	'Heading',
	'subh':	'Subheading',
	'foot':	'Footer',
	'unit':	'Units',
	'colu':	'Column Headers?',
	'sour':	'Source File'
}
CSV_REPORT_DEFAULT_COLUMNS = [
	'type', 'head', 'subh', 'foot', 'unit', 'colu', 'sour'
]

# conversions
def pt2mm(pt=1):
    """72pt -> 25.4mm (1 inch)"""
    return float(pt) * 25.4 / 72.0

def mm2pt(mm=1):
    """25.4mm -> 72pt (1 inch)"""
    return float(mm) * 72.0 / 25.4

def in2pt(inval=1):
    """1in -> 72pt"""
    return float(inval) * 72.0

def cm2pt(cm=1):
    """2.54cm => 72pt (1 inch)"""
    return float(cm) * 72.0 / 2.54

def pt2pt(pt=1):
    """Dummy conversion."""
    return pt

# raw defaults
FEPSILON = 0.0001				# float epsilon
BODYFONT = 'serif 7.0'				# body text
BODYOBLIQUE = 'serif italic 7.0'		# body text oblique
BODYBOLDFONT = 'serif bold 7.0'			# bold body text
MONOSPACEFONT = 'monospace bold 7.0'		# monospaced text
SECTIONFONT = 'sans bold 7.0'			# section headings
SUBHEADFONT = 'serif italic 7.0'		# section subheadings
TITLEFONT = 'sans bold 8.0'			# page title
SUBTITLEFONT = 'sans bold 7.5'			# page subtitle
ANNOTFONT = 'sans oblique 6.0'			# header and footer annotations
PROVFONT = 'sans bold ultra-condensed 90'	# provisonal underlay font
GAMUTSTDFONT = 'sans bold condensed'		# default gamut standard font
GAMUTOBFONT = 'sans bold condensed italic'	# default gamut oblique font
LINE_HEIGHT = mm2pt(5.0)			# body text line height
PAGE_OVERFLOW = mm2pt(3.0)			# tolerated section overflow
SECTION_HEIGHT = mm2pt(5.3)			# height of section title
TWOCOL_WIDTH = mm2pt(75.0)			# width of col on 2 col page
THREECOL_WIDTH = mm2pt(50.0)			# width of col on 3 col page

UNITSMAP = { 'mm':mm2pt,
             'cm':cm2pt,
             'in':in2pt,
             'pt':pt2pt, }

def deg2rad(deg=1):
    """convert degrees to radians."""
    return math.pi * float(deg)/180.0

def pi2rad(ang=1):
    """convert multiple of pi to radians."""
    return math.pi * float(ang)

def rad2rad(ang=1):
    """Dummy converter."""
    return ang

ANGUNITSMAP = { 'dg':deg2rad,
                'pi':pi2rad,
                'rd':rad2rad, }

def str2angle(anglestr=None):
    """From degrees, return an angle in radians -2pi -> 2pi"""
    if anglestr is None:
        anglestr = ''
    units = anglestr.strip()[-2:]
    ukey = units.lower()
    val = anglestr
    if ukey not in ANGUNITSMAP:
        ukey = 'dg'
    else:
        val = anglestr.replace(units, '')
    fval = 0.0
    try:
        fval = float(val)
    except ValueError:
        # ignore float value errors
        pass
    return ANGUNITSMAP[ukey](fval)
    
def str2align(alignstr=None):
    """Return an alignment value 0.0 - 1.0."""
    if alignstr is None:
        alignstr = ''
    ret = 0.5
    try:
        ret = float(alignstr)
        if ret < 0.0:
            ret = 0.0
        elif ret > 1.0:
            ret = 1.0
    except ValueError:
        # ignore float value errors
        pass
    return ret

def str2len(lenstr=None):
    """Return a length in points from the supplied string."""
    if lenstr is None:
        lenstr = ''
    units = lenstr.strip()[-2:]
    ukey = units.lower()
    val = lenstr
    if ukey not in UNITSMAP:
        ukey = 'mm'
    else:
        val = lenstr.replace(units, '')
    fval = 0.0
    try:
        fval = float(val)
    except ValueError:
        # ignore float value errors
        pass
    return UNITSMAP[ukey](fval)

def str2dash(dashstr=None):
    ret = None
    if dashstr:
        dvec = dashstr.split()
        rvec = []
        for d in dvec:
            rvec.append(str2len(d))
        if len(rvec) > 0:
            ret = rvec
    return ret

def str2colour(colstr = None):
    """Return a valid colour from supplied string."""
    ret = [0.0, 0.0, 0.0]
    if colstr:
        cvec = colstr.split(',')
        if len(cvec) == 3:
            try:
                for c in range(0,3):
                    ret[c] = float(cvec[c])
                    if ret[c] < 0.0:
                        ret[c] = 0.0
                    elif ret[c] > 1.0:
                        ret[c] = 1.0
            except ValueError:
                pass
    return ret

def mksectionid(curset, prefix=None):
    """Return a unique id for the section."""
    if prefix is None:
        prefix = ''
    else:
        prefix = prefix.lower().strip()
    if not prefix:
        prefix = 'sec'
        testid = prefix + str(random.randint(1000,9999))
    else:
        testid = prefix
    while testid in curset:
        testid = prefix + str(random.randint(1000,9999))
    return testid

def vecmap(vec=[], maxkey=10):
    """Return a full map for the supplied vector."""
    ret = {}
    for i in range(0,maxkey):
        ret[i] = None
    for i in range(0,len(vec)):
        if vec[i]:
            if isinstance(vec[i], str):
                ret[i] = vec[i].strip()	# why stripped -> for TEMPLATE
            else:
                ret[i] = vec[i]
    return ret

def vecmapstr(vec=[], maxkey=10):
    """Return a full map for the supplied vector, converted to strings."""
    ret = {}
    for i in range(0,maxkey):
        ret[i] = ''
    for i in range(0,len(vec)):
        if vec[i]:
            ret[i] = str(vec[i]).strip()
    return ret

def vec2htmllinkrow(vec=[], xtn=''):
    rowmap = vecmapstr(vec,7)
    cols = []
    cols.append(htlib.td(htlib.escapetext(rowmap[0])))
    if rowmap[4]:
        cols.append(htlib.td(htlib.a(htlib.escapetext(rowmap[2]),
                                      {'href':rowmap[4]+xtn})))
    else:
        cols.append(htlib.td(htlib.escapetext(rowmap[2])))
    cols.append(htlib.td(htlib.escapetext(rowmap[3])))
    return htlib.tr(cols)

def vec2htmlrow(vec=[]):
    rowmap = vecmapstr(vec, 7)
    cols = []
    cols.append(htlib.td(htlib.escapetext(rowmap[0])))	# Rank (left)
    cols.append(htlib.td(htlib.escapetext(rowmap[1]),
                           {'class':'right'}))	# No (right)
    cols.append(htlib.td(htlib.escapetext(rowmap[2])))	# Name (left)
    cols.append(htlib.td(htlib.escapetext(rowmap[3])))	# Cat/Code (left)
    cols.append(htlib.td(htlib.escapetext(rowmap[4]),
                           {'class':'right'}))	# time/gap (right)
    cols.append(htlib.td(htlib.escapetext(rowmap[5]),
                           {'class':'right'}))	# time/gap (right)
    cols.append(htlib.td(htlib.escapetext(rowmap[6])))	# Units (left)
    return htlib.tr(cols)

def vec2htmlhead(vec=[]):
    rowmap = vecmapstr(vec, 7)
    cols = []
    cols.append(htlib.th(htlib.escapetext(rowmap[0])))	# Rank (left)
    cols.append(htlib.th(htlib.escapetext(rowmap[1]),
                           {'class':'right'}))	# No (right)
    cols.append(htlib.th(htlib.escapetext(rowmap[2])))	# Name (left)
    cols.append(htlib.th(htlib.escapetext(rowmap[3])))	# Cat/Code (left)
    cols.append(htlib.th(htlib.escapetext(rowmap[4]),
                           {'class':'right'}))	# time/gap (right)
    cols.append(htlib.th(htlib.escapetext(rowmap[5]),
                           {'class':'right'}))	# time/gap (right)
    cols.append(htlib.th(htlib.escapetext(rowmap[6])))	# Units (left)
    return htlib.tr(cols)

def vec2line(vec=[]):
    ret = []
    for i in vec:
        if i is not None:
            ret.append(str(i))
        else:
            ret.append('')
    return ' '.join(ret).strip() + '   \n'

def csv_colkey(colstr=''):
    return colstr[0:4].lower()

## Section Types
class dual_ittt_startlist(object):
    """Two-up time trial for individual riders (eg track pursuit)."""
    def __init__(self, secid=None):
        self.sectionid = secid
        self.heading = None
        self.status = None
        self.subheading = None
        self.footer = None
        self.colheader = None	# ignored for dual ittt
        self.showheats = False	# show heat labels?
        self.units = None
        self.lines = []
        self.fslbl = 'Front Straight'
        self.bslbl = 'Back Straight'
        self.lcount = 0
        self.pairs = False
        self.h = None

    def serialize(self, rep, sectionid=None):
        """Return a serializable map for JSON export."""
        ret = {}
        ret['sectionid'] = sectionid
        ret['type'] = 'dualittt'
        ret['heading'] = self.heading
        ret['status'] = self.status
        ret['subheading'] = self.subheading
        ret['colheader'] = self.colheader
        ret['footer'] = self.footer
        ret['units'] = self.units
        ret['lines'] = self.lines
        ret['showheats'] = self.showheats
        ret['fslabel'] = self.fslbl
        ret['bslabel'] = self.bslbl
        ret['height'] = self.get_h(rep)
        ret['count'] = self.lcount
        return ret

    def set_record(self, recstr):
        """Set or clear the record string for this event."""
        if recstr:
            if recstr[0].isdigit():	# HACK -> remove later
                self.footer = 'Australian Record: ' + recstr
            else:	# ASSUME prompt provided
                self.footer = recstr
        else:
            self.footer = None

    def set_single(self):
        """Convenience func to make 'single lane'."""
        self.fslbl = ''
        self.bslbl = ''
        self.showheats = False

    def get_h(self, report):
        """Return total height on page of section on report."""
        if self.h is None or len(self.lines) != self.lcount:
            self.h = report.line_height * len(self.lines)
            if self.showheats:	# if heats are shown, double line height
                self.h *= 2
            for r in self.lines:	# account for any team members
                tcnt = 0
                if len(r) > 3 and isinstance(r[3], list):
                    tcnt = len(r[3])
                if len(r) > 7 and isinstance(r[7], list):
                    tcnt = max(tcnt, len(r[7]))
                if tcnt > 0:
                    self.h += tcnt * report.line_height
            if self.heading:
                self.h += report.section_height
            if self.subheading:
                self.h += report.line_height
            if self.fslbl or self.bslbl:
                self.h += report.line_height
            if self.footer:
                self.h += report.line_height
            self.lcount = len(self.lines)
        return self.h

    def truncate(self, remainder, report):
        """Return a copy of the section up to page break."""

        # Special case 1: Entire section will fit on page
        if self.get_h(report) <= (remainder + report.page_overflow):
            return (self, None)

        # Special case 2: Not enough space for minimum content
        chk = dual_ittt_startlist()
        chk.heading = self.heading
        chk.subheading = self.subheading
        chk.colheader = self.colheader
        chk.showheats = self.showheats
        chk.units = self.units
        chk.footer = self.footer
        chk.fslbl = self.fslbl
        chk.bslbl = self.bslbl
        if len(self.lines) <= 4: # special case, keep four or less together
            chk.lines = self.lines[0:]
        else:			 # BUT, don't break before third rider
            chk.lines = self.lines[0:2]
        if chk.get_h(report) > remainder:
            # move entire section onto next page
            return (pagebreak(), self)

        # Standard case - section crosses page break, determines
        # ret: content on current page
        # rem: content on subsequent pages
        ret = dual_ittt_startlist()
        ret.heading = self.heading
        ret.subheading = self.subheading
        ret.colheader = self.colheader
        ret.showheats = self.showheats
        ret.units = self.units
        ret.footer = self.footer
        ret.fslbl = self.fslbl
        ret.bslbl = self.bslbl

        rem = dual_ittt_startlist()
        rem.heading = self.heading
        rem.subheading = self.subheading
        rem.colheader = self.colheader
        rem.showheats = self.showheats
        rem.units = self.units
        rem.footer = self.footer
        rem.fslbl = self.fslbl
        rem.bslbl = self.bslbl

        if rem.heading is not None:
            if rem.heading.rfind('(continued)') < 0:
                rem.heading += ' (continued)'
        seclines = len(self.lines)
        count = 0
        if seclines > 0:
            while count < seclines and count < 3: # don't break until 3rd
                ret.lines.append(self.lines[count])
                count += 1
        while count < seclines:
            if ret.get_h(report) > remainder:
                # pop last line onto rem and break
                rem.lines.append(ret.lines.pop(-1))
                break
            elif seclines - count <= 2: # push min 2 names over to next page
                break
            ret.lines.append(self.lines[count])
            count += 1
        while count < seclines:
            rem.lines.append(self.lines[count])
            count += 1
        return(ret, rem)

    def draw_pdf(self, report):
        """Output a single section to the page."""
        report.c.save()
        if self.heading is not None:
            report.text_cent(report.midpagew, report.h, self.heading,
                           report.fonts['section'])
            report.h += report.section_height
        if self.subheading:
            report.text_cent(report.midpagew, report.h, self.subheading,
                              report.fonts['subhead'])
            report.h += report.line_height
        dolanes = False
        dual = False
        if self.fslbl:
            report.text_cent(report.midpagew-mm2pt(40), report.h, self.fslbl,
                              report.fonts['subhead'])
            dolanes = True
        if self.bslbl:
            report.text_left(report.midpagew+mm2pt(40), report.h, self.bslbl,
                              report.fonts['subhead'])
            dolanes = True
            dual = True		# heading flags presense of back straight
        if dolanes:
            report.h += report.line_height # account for lane label h
        hof = report.h
        lineheight = report.line_height
        if self.showheats:
            lineheight *= 2
        for i in self.lines:
            hof = report.ittt_heat(i, hof, dual, self.showheats)
            #hof += lineheight
            #if self.pairs:
                #hof += lineheight
        if self.footer:
            report.text_cent(report.midpagew, hof, self.footer,
                              report.fonts['subhead'])
            hof += report.line_height
        report.h = hof
        report.c.restore()

    def draw_xls(self, report, worksheet):
        """Output program element to excel worksheet."""
        row = report.h
        if self.heading:
            worksheet.write(row, 2, self.heading.strip(), XS_TITLE)
            row += 1
        if self.subheading:
            worksheet.write(row, 2,
                 self.subheading.replace('\t', '  ').strip(), XS_SUBTITLE)
            row += 2
        else:
            row += 1	# min one clear row between
        dual = False
        if self.bslbl:
            dual = True
        if len(self.lines) > 0:
            rows = []
            for r in self.lines:
                nv = [None, None, None]
                if self.showheats and r[0] and r[0] != '-':
                    nv[0] = 'Heat ' + str(r[0])
                if len(r) > 3:	# front straight
                    nv[1] = r[1]
                    nv[2] = r[2]
                rows.append(nv)	# allow empty
                if len(r) > 3 and isinstance(r[3], list):
                    for tm in r[3]:
                        tv = [None,tm[0],tm[1]]
                        rows.append(tv)
                if len(r) > 7:	# back straight
                    nv = [None, r[5], r[6]]
                    rows.append(nv)
                elif dual:
                    rows.append([None, None, '[No Rider]'])
                if len(r) > 7 and isinstance(r[7], list):
                    for tm in r[7]:
                        tv = [None,tm[0],tm[1]]
                        rows.append(tv)
                    
            for rw in rows:
                l = vecmapstr(rw)
                # todo: apply styles to whole doc?
                worksheet.write(row, 0, l[0], XS_LEFT)
                worksheet.write(row, 1, l[1], XS_RIGHT)
                worksheet.write(row, 2, l[2], XS_LEFT)
                worksheet.write(row, 3, l[3], XS_LEFT)
                worksheet.write(row, 4, l[4], XS_RIGHT)
                worksheet.write(row, 5, l[5], XS_RIGHT)
                worksheet.write(row, 6, l[6], XS_LEFT)
                row += 1
            row += 1
        if self.footer:
            worksheet.write(row, 2, self.footer.strip(), XS_SUBTITLE)
            row += 2
        report.h = row
        return None

    def draw_text(self, report, f, xtn):
        """Output program element in markdown."""
        if self.heading:
            f.write(htlib.h3(htlib.escapetext(self.heading.strip())) + '\n\n')
        if self.subheading:
            f.write(htlib.p(htlib.escapetext(self.subheading.strip()), 
                            {'class':'lead'}) + '\n\n')
        dual = False
        if self.bslbl:
            dual = True
        if len(self.lines) > 0:
            rows = []
            for r in self.lines:
                nv = [None, None, None]
                if self.showheats and r[0] and r[0] != '-':
                    nv[0] = 'Heat ' + str(r[0]) + ':'
                if len(r) > 3:	# front straight
                    nv[1] = r[1]
                    nv[2] = r[2]
                rows.append(nv)
                if len(r) > 3 and isinstance(r[3], list):
                    for tm in r[3]:
                        tv = [None,tm[0],tm[1]]
                        rows.append(tv)
                if len(r) > 7:	# back straight
                    nv = [None, r[5], r[6]]
                    rows.append(nv)
                elif dual:
                    rows.append([None, None, '[No Rider]'])
                if len(r) > 7 and isinstance(r[7], list):
                    for tm in r[7]:
                        tv = [None,tm[0],tm[1]]
                        rows.append(tv)
            trows = []
            for l in rows:
                trows.append(vec2htmlrow(l))
            f.write(htlib.table(htlib.tbody(trows),
                  {'class':'table table-striped table-condensed',
                   'style':'width: auto'}))
            f.write('\n\n')

        if self.footer:
            f.write(self.footer.strip() + '\n\n')
        return False

class signon_list(object):
    def __init__(self, secid=None):
        self.sectionid = secid
        self.status = None
        self.heading = None
        self.subheading = None
        self.colheader = None	# ignored for all signon
        self.footer = None
        self.units = None
        self.lineheight = None
        self.lines = []
        self.lcount = 0
        self.h = None

    def serialize(self, rep, sectionid=None):
        """Return a serializable map for JSON export."""
        ret = {}
        ret['sectionid'] = sectionid
        ret['type'] = 'signon'
        ret['heading'] = self.heading
        ret['status'] = self.status
        ret['subheading'] = self.subheading
        ret['colheader'] = self.colheader
        ret['footer'] = self.footer
        ret['units'] = self.units
        ret['lines'] = self.lines
        ret['height'] = self.get_h(rep)
        ret['count'] = self.lcount
        return ret

    def get_h(self, report):
        """Return total height on page of section on report."""
        if self.h is None or len(self.lines) != self.lcount:
            if self.lineheight is None:
                self.lineheight = report.line_height + mm2pt(1.0)
            self.h = 2.0 * self.lineheight * math.ceil(0.5 * len(self.lines))
            if self.heading:
                self.h += report.section_height
            if self.subheading:
                self.h += report.line_height
            if self.footer:
                self.h += report.line_height
            self.lcount = len(self.lines)
        return self.h

    def truncate(self, remainder, report):
        """Return a copy of the section up to page break."""

        # Special case 1: Entire section will fit on page
        if self.get_h(report) <= (remainder + report.page_overflow):
            return (self, None)

        # Special case 2: Not enough space for minimum content
        chk = signon_list()
        chk.heading = self.heading
        chk.subheading = self.subheading
        chk.footer = self.footer
        chk.lineheight = self.lineheight
        if len(self.lines) <= 8: # special case, keep first <=8 together
            chk.lines = self.lines[0:]
        else:
            chk.lines = self.lines[0:4]	# but don't break until 4 names
        if chk.get_h(report) > remainder:
            # move entire section onto next page
            return (pagebreak(), self)

        # Standard case - section crosses page break, determines
        # ret: content on current page
        # rem: content on subsequent pages
        ret = signon_list()
        rem = signon_list()
        ret.heading = self.heading
        ret.subheading = self.subheading
        ret.footer = self.footer
        ret.lineheight = self.lineheight
        rem.heading = self.heading
        rem.subheading = self.subheading
        rem.footer = self.footer
        rem.lineheight = self.lineheight
        if rem.heading is not None:
            if rem.heading.rfind('(continued)') < 0:
                rem.heading += ' (continued)'
        seclines = len(self.lines)
        count = 0
        if seclines > 0:
            while count < seclines and count < 4: # don't break until 4th
                ret.lines.append(self.lines[count])
                count += 1
        while count < seclines:
            if ret.get_h(report) > remainder:
                # pop last line onto rem and break
                rem.lines.append(ret.lines.pop(-1))
                break
            elif seclines - count <= 3: # push min 4 names over to next page
                break
            ret.lines.append(self.lines[count])
            count += 1
        while count < seclines:
            rem.lines.append(self.lines[count])
            count += 1
        return(ret, rem)

    def draw_pdf(self, report):
        """Output a single section to the page."""
        report.c.save()
        if self.heading:
            report.text_cent(report.midpagew, report.h, self.heading,
                           report.fonts['section'])
            report.h += report.section_height
        if self.subheading:
            report.text_cent(report.midpagew, report.h, self.subheading,
                              report.fonts['subhead'])
            report.h += report.line_height

        colof = report.body_left
        hof = report.h
        collen = int(math.ceil(0.5 * len(self.lines)))
        colcnt = 0
        if len(self.lines) > 0:
            for i in self.lines[0:collen]:
                if len(i) > 2:
                    report.sign_box(i, colof, hof, self.lineheight,
                                       colcnt%2)
                hof += self.lineheight + self.lineheight
                colcnt += 1
            hof = report.h
            colof = report.body_right-report.twocol_width
            #colof = report.midpagew+mm2pt(2.0)
            colcnt = 0
            for i in self.lines[collen:]:
                if len(i) > 2:
                    report.sign_box(i, colof, hof, self.lineheight,
                                       (colcnt+1)%2)
                hof += self.lineheight + self.lineheight
                colcnt += 1
        report.h += 2.0 * collen * self.lineheight
        if self.footer:
            report.text_cent(report.midpagew, report.h, self.footer,
                              report.fonts['subhead'])
            report.h += report.line_height

    def draw_xls(self, report, worksheet):
        """Output program element to excel worksheet."""
        row = report.h
        if self.heading:
            worksheet.write(row, 2, self.heading.strip(), XS_TITLE)
            row += 1
        if self.subheading:
            worksheet.write(row, 2,
                 self.subheading.replace('\t', '  ').strip(), XS_SUBTITLE)
            row += 2
        else:
            row += 1	# min one clear row between
 
        if len(self.lines) > 0:
            rows = []
            for r in self.lines:
                nv = r[0:6]
                if len(nv) == 2:
                    nv = [nv[0], None, nv[1]]
                rows.append(vecmapstr(nv, 7))
            for l in rows:
                # todo: apply styles to whole doc?
                worksheet.write(row, 0, l[0], XS_LEFT)
                worksheet.write(row, 1, l[1], XS_RIGHT)
                worksheet.write(row, 2, l[2], XS_LEFT)
                worksheet.write(row, 3, l[3], XS_LEFT)
                worksheet.write(row, 4, l[4], XS_RIGHT)
                worksheet.write(row, 5, l[5], XS_RIGHT)
                worksheet.write(row, 6, l[6], XS_LEFT)
                row += 1
            row += 1
        if self.footer:
            worksheet.write(row, 2, self.footer.strip(), XS_SUBTITLE)
            row += 2
        report.h = row
        return None

    def draw_text(self, report, f, xtn):
        """Write out a section in markdown."""
        if self.heading:
            f.write(htlib.h3(htlib.escapetext(self.heading.strip())) + '\n\n')
        if self.subheading:
            f.write(htlib.p(htlib.escapetext(self.subheading.strip()),
                            {'class':'lead'}) + '\n\n')
        if len(self.lines) > 0:
            rows = []
            for r in self.lines:
                nv = r[0:6]
                if len(nv) == 2:
                    nv = [nv[0], None, nv[1]]
                rows.append(nv)
            trows = []
            for l in rows:
                trows.append(vec2htmlrow(l))
            f.write(htlib.table(htlib.tbody(trows),
                  {'class':'table table-striped table-condensed',
                   'style':'width: auto'}))
            f.write('\n\n')
        if self.footer:
            f.write(self.footer.strip() + '\n\n')
        return False

class twocol_startlist(object):
    def __init__(self, secid=None):
        self.sectionid = secid
        self.heading = None
        self.status = None
        self.subheading = None
        self.footer = None
        self.timestr = None
        self.lines = []
        self.lcount = 0
        self.even = False
        self.preh = None
        self.h = None
        
    def serialize(self, rep, sectionid=None):
        """Return a serializable map for JSON export."""
        ret = {}
        ret['sectionid'] = sectionid
        ret['type'] = 'twocol'
        ret['heading'] = self.heading
        ret['status'] = self.status
        ret['subheading'] = self.subheading
        ret['footer'] = self.footer
        ret['lines'] = self.lines
        ret['timestr'] = self.timestr
        ret['height'] = self.get_h(rep)
        ret['count'] = self.lcount
        return ret

    def get_h(self, report):
        """Return total height on page of section on report."""
        if self.h is None or len(self.lines) != self.lcount:
            self.preh = 0.0
            collen = math.ceil(0.5 * len(self.lines))
            if self.even and collen % 2:
                collen += 1	# force an even number of rows in first column.
            self.h = report.line_height * collen
            if self.heading:
                self.h += report.section_height
                self.preh += report.section_height
            if self.subheading:
                self.h += report.line_height
                self.preh += report.line_height
            if self.timestr:
                self.h += report.line_height
                self.preh += report.line_height
            if self.footer:
                self.h += report.line_height
                self.preh += report.line_height
            self.lcount = len(self.lines)
        return self.h

    def truncate(self, remainder, report):
        """Return a copy of the section up to page break."""
        # program event sections do not break ... 
        if self.get_h(report) <= (remainder + report.page_overflow):
            return (self, None)
        else:
            if report.pagefrac() < FEPSILON:	# avoid error
                # there's a whole page's worth of space here, but a
                # break is required
                bodyh = remainder - self.preh # preh comes from get_h
                maxlines = 2 * int(bodyh / report.line_height) # floor
                # ret: content on current page
                # rem: content on subsequent pages
                ret = twocol_startlist()
                rem = twocol_startlist()
                ret.heading = self.heading
                ret.subheading = self.subheading
                ret.footer = self.footer
                if ret.footer:
                    ret.footer += ' Continued over\u2026'
                ret.timestr = self.timestr
                ret.lines = self.lines[0:maxlines]
                rem.heading = self.heading
                rem.subheading = self.subheading
                rem.footer = self.footer
                rem.timestr = self.timestr
                if rem.heading:
                    if rem.heading.rfind('(continued)') < 0:
                        rem.heading += ' (continued)'
                rem.lines = self.lines[maxlines:]
                return (ret, rem)
            else:
                # we are somewhere on the page - insert break and try again
                return (pagebreak(), self)

    def draw_pdf(self, report):
        """Output a single section to the page."""
        report.c.save()
        if self.heading:
            report.text_cent(report.midpagew, report.h, self.heading,
                           report.fonts['section'])
            report.h += report.section_height
        if self.subheading:
            report.text_cent(report.midpagew, report.h, self.subheading,
                              report.fonts['subhead'])
            report.h += report.line_height

        #colof = report.body_left-mm2pt(10.0)
        colof = report.body_left
        hof = report.h
        collen = int(math.ceil(0.5 * len(self.lines)))
        if self.even and collen % 2:
            collen += 1	# force an even number of rows in first column.
        if len(self.lines) > 0:
            for i in self.lines[0:collen]:
                if len(i) > 2:
                    report.rms_rider(i, colof, hof)
                hof += report.line_height
            hof = report.h
            #colof = report.midpagew-mm2pt(5.0)
            colof = report.midpagew+mm2pt(2.0)
            for i in self.lines[collen:]:
                if len(i) > 2:
                    report.rms_rider(i, colof, hof)
                hof += report.line_height
        report.h += collen * report.line_height

        if self.timestr:
            baseline = report.get_baseline(report.h)
            report.text_right(report.body_right - mm2pt(21.0), report.h,
                              self.timestr, report.fonts['subhead'])
            report.drawline(report.body_right - mm2pt(20.0), baseline,
                            report.body_right, baseline)
            report.h += report.line_height
        if self.footer:
            report.text_cent(report.midpagew, report.h, self.footer,
                              report.fonts['subhead'])
            report.h += report.line_height
        report.c.restore()

    def draw_xls(self, report, worksheet):
        """Output program element to excel worksheet."""
        row = report.h
        if self.heading:
            worksheet.write(row, 2, self.heading.strip(), XS_TITLE)
            row += 1
        if self.subheading:
            worksheet.write(row, 2,
                 self.subheading.replace('\t', '  ').strip(), XS_SUBTITLE)
            row += 2
        else:
            row += 1	# min one clear row between
 
        if len(self.lines) > 0:
            rows = []
            for r in self.lines:
                nv = r[0:6]
                if len(nv) == 2:
                    nv = [nv[0], None, nv[1]]
                rows.append(vecmapstr(nv, 7))
            for l in rows:
                # todo: apply styles to whole doc?
                worksheet.write(row, 0, l[0], XS_LEFT)
                worksheet.write(row, 1, l[1], XS_RIGHT)
                worksheet.write(row, 2, l[2], XS_LEFT)
                worksheet.write(row, 3, l[3], XS_LEFT)
                worksheet.write(row, 4, l[4], XS_RIGHT)
                worksheet.write(row, 5, l[5], XS_RIGHT)
                worksheet.write(row, 6, l[6], XS_LEFT)
                row += 1
            row += 1
        if self.footer:
            worksheet.write(row, 2, self.footer.strip(), XS_SUBTITLE)
            row += 2
        report.h = row
        return None

    def draw_text(self, report, f, xtn):
        """Write out a section in markdown."""
        if self.heading:
            f.write(htlib.h3(htlib.escapetext(self.heading.strip())) + '\n\n')
        if self.subheading:
            f.write(htlib.p(htlib.escapetext(self.subheading.strip()),
                            {'class':'lead'}) + '\n\n')
        if len(self.lines) > 0:
            rows = []
            for r in self.lines:
                nv = r[0:6]
                if len(nv) == 2:
                    nv = [nv[0], None, nv[1]]
                rows.append(nv)
            trows = []
            for l in rows:
                trows.append(vec2htmlrow(l))
            f.write(htlib.table(htlib.tbody(trows),
                  {'class':'table table-striped table-condensed',
                   'style':'width: auto'}))
            f.write('\n\n')
        if self.footer:
            f.write(self.footer.strip() + '\n\n')
        return False

class sprintround(object):
    def __init__(self, secid=None):
        self.sectionid = secid
        self.heading = None
        self.status = None
        self.subheading = None
        self.colheader = None
        self.units = None
        self.footer = None
        self.lines = []		 # maps to 'heats', include riders?
        self.lcount = 0
        self.h = None

    def serialize(self, rep, sectionid=None):
        """Return a serializable map for JSON export."""
        ret = {}
        ret['sectionid'] = sectionid
        ret['type'] = 'sprintround'
        ret['heading'] = self.heading
        ret['status'] = self.status
        ret['subheading'] = self.subheading
        ret['colheader'] = self.colheader
        ret['footer'] = self.footer
        ret['units'] = self.units
        ret['lines'] = self.lines
        ret['height'] = self.get_h(rep)
        ret['count'] = self.lcount
        return ret

    def get_h(self, report):
        """Return total height on page of section on report."""
        if self.h is None or len(self.lines) != self.lcount:
            self.h = report.line_height * len(self.lines) # one per line?
            if self.heading:
                self.h += report.section_height
            if self.subheading:
                self.h += report.line_height
            if self.footer:
                self.h += report.line_height
            self.lcount = len(self.lines)
        return self.h

    def truncate(self, remainder, report):
        """Return a copy of the section up to page break."""
        # program event sections do not break ... 
        if self.get_h(report) <= (remainder + report.page_overflow):
            return (self, None)
        else:
            if report.pagefrac() < FEPSILON:
                raise RuntimeWarning('Section ' + repr(self.heading)
                          + ' will not fit on a page and will not break.')
            # move entire section onto next page
            return (pagebreak(), self)

    def draw_pdf(self, report):
        """Output a single section to the page."""
        report.c.save()
        if self.heading is not None:
            report.text_cent(report.midpagew, report.h, self.heading,
                           report.fonts['section'])
            report.h += report.section_height
        if self.subheading is not None:
            report.text_cent(report.midpagew, report.h, self.subheading,
                           report.fonts['subhead'])
            report.h += report.line_height
        hof = report.h
        if len(self.lines) > 0:
            for i in self.lines:
                heat = ''
                if i[0]:
                    heat = i[0]
                if heat:
                    report.text_left(report.body_left, hof,
                                     heat, report.fonts['subhead']) 
                report.sprint_rider(i[1], report.body_left + mm2pt(14), hof)
                report.sprint_rider(i[2], report.midpagew + mm2pt(4), hof)
                vstr = 'v'
                if i[1][0] and i[2][0]:	# assume result in order...
                    vstr = 'def'
                if i[2][0] == ' ':	# hack for bye
                    vstr = None
                if vstr:
                    report.text_cent(report.midpagew, hof,
                                     vstr, report.fonts['subhead']) 
                timestr = ''
                if len(i) > 3 and i[3]:
                    timestr = i[3]	# probably already have a result
                if timestr:
                    report.text_right(report.body_right, hof,
                                      timestr, report.fonts['body']) 
                else:
                    baseline = report.get_baseline(hof)
                    report.drawline(report.body_right - mm2pt(10),
                                    baseline,
                                    report.body_right,
                                    baseline)
                hof += report.line_height
        report.h = hof
        if self.footer:
            report.text_cent(report.midpagew, report.h, self.footer,
                              report.fonts['subhead'])
            report.h += report.line_height
        report.c.restore()

    def draw_xls(self, report, worksheet):
        """Output program element to excel worksheet."""
        row = report.h
        if self.heading:
            worksheet.write(row, 2, self.heading.strip(), XS_TITLE)
            row += 1
        if self.subheading:
            worksheet.write(row, 2,
                 self.subheading.replace('\t', '  ').strip(), XS_SUBTITLE)
            row += 2
        else:
            row += 1	# min one clear row between
        if len(self.lines) > 0:
            rows = []
            for c in self.lines:	# each row is a pair/contest
                # 'a' rider
                rows.append([None, None, c[0], None, None])	# contest id)
                av = [None, None, None, None, None]
                av[0] = c[1][0]
                av[1] = c[1][1]
                av[2] = c[1][2]
                av[3] = c[1][3]
                if len(c) > 3 and c[3]:
                    av[4] = c[3]	# place 200m time in info col
                rows.append(av)
                # 'b' rider
                bv = [None, None, None, None, None]
                bv[0] = c[2][0]
                bv[1] = c[2][1]
                bv[2] = c[2][2]
                bv[3] = c[2][3]
                rows.append(bv)
            for rw in rows:
                l = vecmapstr(rw)
                # todo: apply styles to whole doc?
                worksheet.write(row, 0, l[0], XS_LEFT)
                worksheet.write(row, 1, l[1], XS_RIGHT)
                worksheet.write(row, 2, l[2], XS_LEFT)
                worksheet.write(row, 3, l[3], XS_LEFT)
                worksheet.write(row, 4, l[4], XS_RIGHT)
                worksheet.write(row, 5, l[5], XS_RIGHT)
                worksheet.write(row, 6, l[6], XS_LEFT)
                row += 1
            row += 1
        if self.footer:
            worksheet.write(row, 2, self.footer.strip(), XS_SUBTITLE)
            row += 2
        report.h = row
        return None

    def draw_text(self, report, f, xtn):
        """Output program element in markdown."""
        if self.heading:
            f.write(htlib.h3(htlib.escapetext(self.heading.strip())) + '\n\n')
        if self.subheading:
            f.write(htlib.p(htlib.escapetext(self.subheading.strip()),
                            {'class':'lead'}) + '\n\n')
        if len(self.lines) > 0:
            rows = []
            for c in self.lines:	# each row is a pair/contest
                # 'a' rider
                rows.append([None, None, c[0], None, None])	# contest id)
                av = [None, None, None, None, None]
                av[0] = c[1][0]
                av[1] = c[1][1]
                av[2] = c[1][2]
                av[3] = c[1][3]
                if len(c) > 3 and c[3]:
                    av[4] = c[3]	# place 200m time in info col
                rows.append(av)
                # 'b' rider
                bv = [None, None, None, None, None]
                bv[0] = c[2][0]
                bv[1] = c[2][1]
                bv[2] = c[2][2]
                bv[3] = c[2][3]
                rows.append(bv)
            trows = []
            for l in rows:
                trows.append(vec2htmlrow(l))
            f.write(htlib.table(htlib.tbody(trows),
                  {'class':'table table-striped table-condensed',
                   'style':'width: auto'}))
            f.write('\n\n')
        if self.footer:
            f.write(self.footer.strip() + '\n\n')
        return ''

class sprintfinal(object):
    def __init__(self, secid=None):
        self.sectionid = secid
        self.status = None
        self.heading = None
        self.subheading = None
        self.colheader = None
        self.units = None
        self.footer = None
        self.lines = []		 # maps to 'contests'
        self.lcount = 0
        self.h = None
        
    def serialize(self, rep, sectionid=None):
        """Return a serializable map for JSON export."""
        ret = {}
        ret['sectionid'] = sectionid
        ret['type'] = 'sprintfinal'
        ret['heading'] = self.heading
        ret['status'] = self.status
        ret['subheading'] = self.subheading
        ret['colheader'] = self.colheader
        ret['footer'] = self.footer
        ret['units'] = self.units
        ret['lines'] = self.lines
        ret['height'] = self.get_h(rep)
        ret['count'] = self.lcount
        return ret

    def get_h(self, report):
        """Return total height on page of section."""
        if self.h is None or len(self.lines) != self.lcount:
            self.h = report.line_height * 3.0 * len(self.lines)
            if self.heading:
                self.h += report.section_height
            if self.subheading:
                self.h += report.line_height
            if self.footer:
                self.h += report.line_height
            self.lcount = len(self.lines)
        return self.h

    def truncate(self, remainder, report):
        """Return a copy of the section up to page break."""
        # program event sections do not break ... 
        if self.get_h(report) <= (remainder + report.page_overflow):
            return (self, None)
        else:
            if report.pagefrac() < FEPSILON:
                raise RuntimeWarning('Section ' + repr(self.heading)
                          + ' will not fit on a page and will not break.')
            # move entire section onto next page
            return (pagebreak(), self)

    def draw_pdf(self, report):
        """Output a single section to the page."""
        report.c.save()
        if self.heading is not None:
            report.text_cent(report.midpagew, report.h, self.heading,
                           report.fonts['section'])
            report.h += report.section_height
        if self.subheading is not None:
            report.text_cent(report.midpagew, report.h, self.subheading,
                           report.fonts['subhead'])
            report.h += report.line_height
        hof = report.h
        if len(self.lines) > 0:
            for i in self.lines:
                hw = mm2pt(20)
                hl = report.midpagew + hw
                h1t = hl + 0.5*hw
                h2t = h1t + hw
                h12 = hl + hw
                h3t = h2t + hw
                h23 = h12 + hw
                hr = hl + 3.0*hw

                # place heat headings
                report.text_cent(h1t, hof, 'Heat 1', report.fonts['subhead']) 
                report.text_cent(h2t, hof, 'Heat 2', report.fonts['subhead']) 
                report.text_cent(h3t, hof, 'Heat 3', report.fonts['subhead']) 
                hof += report.line_height

                heat = ''
                if i[0]:
                    heat = i[0]
                if heat:
                    report.text_left(report.body_left, hof,
                                     heat, report.fonts['subhead']) 

                ht = hof
                bl = report.get_baseline(hof)
                hb = report.get_baseline(hof + report.line_height)
                # draw heat lines
                report.drawline(hl, bl, hr, bl)
                report.drawline(h12, ht, h12, hb)
                report.drawline(h23, ht, h23, hb)

                # draw all the "a" rider info
                report.sprint_rider(i[1], report.body_left+hw, hof)
                if i[1][4]:
                    report.text_cent(h1t, hof, i[1][4], report.fonts['body']) 
                if i[1][5]:
                    report.text_cent(h2t, hof, i[1][5], report.fonts['body'])
                if i[1][6]:
                    report.text_cent(h3t, hof, i[1][6], report.fonts['body'])
                #if len(i[2]) > 7 and i[1][7]:
                    #report.text_left(hl, hof, i[1][7], report.fonts[u'body'])
                hof += report.line_height

                # draw all the "b" rider info
                report.sprint_rider(i[2], report.body_left+hw, hof)
                if i[2][4]:
                    report.text_cent(h1t, hof, i[2][4], report.fonts['body']) 
                if i[2][5]:
                    report.text_cent(h2t, hof, i[2][5], report.fonts['body'])
                if i[2][6]:
                    report.text_cent(h3t, hof, i[2][6], report.fonts['body'])
                #if len(i[2]) > 7 and i[2][7]:
                    #report.text_left(hl, hof, i[2][7], report.fonts[u'body'])
                hof += report.line_height

        report.h = hof
        if self.footer:
            report.text_cent(report.midpagew, report.h, self.footer,
                              report.fonts['subhead'])
            report.h += report.line_height
        report.c.restore()

    def draw_xls(self, report, worksheet):
        """Output program element to excel worksheet."""
        row = report.h
        if self.heading:
            worksheet.write(row, 2, self.heading.strip(), XS_TITLE)
            row += 1
        if self.subheading:
            worksheet.write(row, 2,
                 self.subheading.replace('\t', '  ').strip(), XS_SUBTITLE)
            row += 2
        else:
            row += 1	# min one clear row between
        if len(self.lines) > 0:
            rows = []
            rows.append([None,None,None,'Heat 1','Heat 2','Heat 3'])
            for c in self.lines:	# each row is a pair/contest
                # 'a' rider
                av = [c[1][j] for j in [0,1,2,4,5,6]]	# skip info col
                av[0] = c[0]
                rows.append(av)
                # 'b' rider
                bv = [c[2][j] for j in [0,1,2,4,5,6]]
                bv[0] = None
                rows.append(bv)
                rows.append([])
            for rw in rows:
                l = vecmapstr(rw)
                # todo: apply styles to whole doc?
                worksheet.write(row, 0, l[0], XS_LEFT)	# contest
                worksheet.write(row, 1, l[1], XS_RIGHT)	# no
                worksheet.write(row, 2, l[2], XS_LEFT)  # name
                worksheet.write(row, 3, l[3], XS_RIGHT)  # heat 1
                worksheet.write(row, 4, l[4], XS_RIGHT) # heat 2
                worksheet.write(row, 5, l[5], XS_RIGHT) # heat 3
                #worksheet.write(row, 6, l[6], XS_LEFT)	# comment?
                row += 1
            row += 1
        if self.footer:
            worksheet.write(row, 2, self.footer.strip(), XS_SUBTITLE)
            row += 2
        report.h = row
        return None

    def draw_text(self, report, f, xtn):
        """Output program element in markdown."""
        if self.heading:
            f.write(htlib.h3(htlib.escapetext(self.heading.strip())) + '\n\n')
        if self.subheading:
            f.write(htlib.p(htlib.escapetext(self.subheading.strip()),
                            {'class':'lead'}) + '\n\n')
        if len(self.lines) > 0:
            rows = []
            rows.append([None,None,None,'Heat 1','Heat 2','Heat 3'])
            for c in self.lines:	# each row is a pair/contest
                # 'a' rider
                #rows.append([None,None,u'Heat 1',u'Heat 2',u'Heat 3'])
                av = [c[1][j] for j in [0,1,2,4,5,6]]	# skip info col
                av[0] = c[0]
                rows.append(av)
                # 'b' rider
                bv = [c[2][j] for j in [0,1,2,4,5,6]]
                bv[0] = None
                rows.append(bv)
                rows.append([])
            trows = []
            for l in rows:
                trows.append(vec2htmlrow(l))
            f.write(htlib.table(htlib.tbody(trows),
                  {'class':'table table-striped table-condensed',
                   'style':'width: auto'}))
            f.write('\n\n')
        if self.footer:
            f.write(self.footer.strip() + '\n\n')
        return ''

class rttstartlist(object):
    """Time trial start list."""
    def __init__(self, secid=None):
        self.sectionid = secid
        self.heading = None
        self.status = None
        self.subheading = None
        self.colheader = None
        self.footer = None
        self.units = None
        self.lines = []
        self.lcount = 0
        self.h = None

    def serialize(self, rep, sectionid=None):
        """Return a serializable map for JSON export."""
        ret = {}
        ret['sectionid'] = sectionid
        ret['type'] = 'rttstartlist'
        ret['heading'] = self.heading
        ret['status'] = self.status
        ret['subheading'] = self.subheading
        ret['colheader'] = self.colheader
        ret['footer'] = self.footer
        ret['units'] = self.units
        ret['lines'] = self.lines
        ret['height'] = self.get_h(rep)
        ret['count'] = self.lcount
        return ret

    def get_h(self, report):
        """Return total height on page of section on report."""
        if self.h is None or len(self.lines) != self.lcount:
            self.h = report.line_height * len(self.lines)
            if self.colheader:	# colheader is written out with body
                self.h += report.line_height
            if self.heading:
                self.h += report.section_height
            if self.subheading:
                self.h += report.line_height
            if self.footer:
                self.h += report.line_height
            self.lcount = len(self.lines)
        return self.h

    def truncate(self, remainder, report):
        """Return a copy of the section up to page break."""
        # Special case 1: Entire section will fit on page
        if self.get_h(report) <= (remainder + report.page_overflow):
            return (self, None)

        # Special case 2: Not enough space for minimum content
        chk = rttstartlist()
        chk.heading = self.heading
        chk.subheading = self.subheading
        chk.colheader = self.colheader
        chk.footer = self.footer
        if len(self.lines) <= 4: # special case, keep four or less together
            chk.lines = self.lines[0:]
        else:			 # BUT, don't break before third rider
            chk.lines = self.lines[0:2]
        if chk.get_h(report) > remainder:
            # move entire section onto next page
            return (pagebreak(), self)

        # Standard case - section crosses page break, determines
        # ret: content on current page
        # rem: content on subsequent pages
        ret = rttstartlist()
        rem = rttstartlist()
        ret.heading = self.heading
        ret.subheading = self.subheading
        ret.colheader = self.colheader
        ret.footer = self.footer
        rem.heading = self.heading
        rem.subheading = self.subheading
        rem.colheader = self.colheader
        rem.footer = self.footer
        if rem.heading is not None:
            if rem.heading.rfind('(continued)') < 0:
                rem.heading += ' (continued)'
        seclines = len(self.lines)
        count = 0
        if seclines > 0:
            while count < seclines and count < 3: # don't break until 3rd
                ret.lines.append(self.lines[count])
                count += 1
        while count < seclines:
            if ret.get_h(report) > remainder:
                # pop last line onto rem and break
                rem.lines.append(ret.lines.pop(-1))
                break
            elif seclines - count <= 2: # push min 2 names over to next page
                break
            ret.lines.append(self.lines[count])
            count += 1
        while count < seclines:
            rem.lines.append(self.lines[count])
            count += 1
        return(ret, rem)

    def draw_pdf(self, report):
        """Output a single section to the page."""
        report.c.save()
        if self.heading:
            report.text_cent(report.midpagew, report.h, self.heading,
                           report.fonts['section'])
            report.h += report.section_height
        if self.subheading:
            report.text_cent(report.midpagew, report.h, self.subheading,
                           report.fonts['subhead'])
            report.h += report.line_height
        cnt = 1
        if len(self.lines) > 0:
            if self.colheader:
                report.h += report.rttstart_row(report.h, self.colheader)
            for r in self.lines:
                if len(r) > 5:
                    if r[5] is not None and r[5].lower() == 'pilot':
                        r[5] = 'Pilot'
                    elif not (r[0] or r[1] or r[2] or r[3]):
                        cnt = 0	# empty row?
                    else:
                        cnt += 1
                else:
                    cnt = 0	# blank all 'empty' lines
                report.h += report.rttstart_row(report.h, r, cnt%2)
                ##TODO: if criteria met to change riderno:
        if self.footer:
            report.text_cent(report.midpagew, report.h, self.footer,
                              report.fonts['subhead'])
            report.h += report.line_height
        report.c.restore()

    def draw_xls(self, report, worksheet):
        """Output program element to excel worksheet."""
        row = report.h
        if self.heading:
            worksheet.write(row, 2, self.heading.strip(), XS_TITLE)
            row += 1
        if self.subheading:
            worksheet.write(row, 2, self.subheading.strip(), XS_SUBTITLE)
            row += 2
        else:
            row += 1
        if len(self.lines) > 0:
            rows = []
            if self.colheader:
                rows.append(vecmapstr(self.colheader,7))
            for r in self.lines:
                nv = r[0:6]
                if len(nv) == 2:
                    nv = [nv[0], None, nv[1]]
                rows.append(vecmapstr(nv, 7))
            for l in rows:
                # todo: apply styles to whole doc?
                worksheet.write(row, 0, l[0], XS_LEFT)
                worksheet.write(row, 1, l[1], XS_RIGHT)
                worksheet.write(row, 2, l[2], XS_LEFT)
                worksheet.write(row, 3, l[3], XS_LEFT)
                worksheet.write(row, 4, l[4], XS_RIGHT)
                worksheet.write(row, 5, l[5], XS_RIGHT)
                worksheet.write(row, 6, l[6], XS_LEFT)
                row += 1
            row += 1
        if self.footer:
            worksheet.write(row, 2, self.footer.strip(), XS_SUBTITLE)
            row += 2
        report.h = row
        return None

    def draw_text(self, report, f, xtn):
        """Write out a section in markdown."""
        if self.heading:
            f.write(htlib.h3(htlib.escapetext(self.heading.strip())) + '\n\n')
        if self.subheading:
            f.write(htlib.p(htlib.escapetext(self.subheading.strip()),
                            {'class':'lead'}) + '\n\n')
        if len(self.lines) > 0:
            rows = []
            if self.colheader:
                rows.append(self.colheader)
            for r in self.lines:
                nv = r[0:6]
                if len(nv) == 2:
                    nv = [nv[0], None, nv[1]]
                rows.append(nv)
            trows = []
            for l in rows:
                trows.append(vec2htmlrow(l))
            f.write(htlib.table(htlib.tbody(trows),
                  {'class':'table table-striped table-condensed',
                   'style':'width: auto'}))
            f.write('\n\n')
        if self.footer:
            f.write(self.footer.strip() + '\n\n')
        return None

class bullet_text(object):
    """List of bullet items, each one a non-breaking pango para."""
    def __init__(self, secid=None):
        self.sectionid = secid
        self.status = None
        self.heading = None	# scalar
        self.subheading = None	# scalar
        self.footer = None
        self.units = None
        self.colheader = None
        self.lines = []		# list of sections: [bullet,para]
        self.lcount = 0		# last count of lines/len
        self.bullet = '\u2022'	# bullet type	?is this the way?
        self.width = None	# allow override of width
        self.h = None		# computed height on page

    def serialize(self, rep, sectionid=None):
        """Return a serializable map for JSON export."""
        ret = {}
        ret['sectionid'] = sectionid
        ret['type'] = 'bullet'
        ret['heading'] = self.heading
        ret['status'] = self.status
        ret['subheading'] = self.subheading
        ret['colheader'] = self.colheader
        ret['footer'] = self.footer
        ret['units'] = self.units
        ret['lines'] = self.lines
        ret['bullet'] = self.bullet
        ret['height'] = self.get_h(rep)
        ret['count'] = self.lcount
        return ret

    def get_h(self, report):
        """Return total height on page of section on report."""
        if self.h is None or len(self.lines) != self.lcount:
            if self.width is None:	# override by caller allowed
                self.width = report.body_width - mm2pt(15+10)
            self.h = 0
            if self.heading:
                self.h += report.section_height
            if self.subheading:
                self.h += report.line_height
            if self.footer:
                self.h += report.line_height
            for line in self.lines:
                bh = report.line_height
                ph = 0
                if line[1] and report.p is not None:
                    ph = report.paragraph_height(line[1], self.width)
                self.h += max(bh, ph)	# enforce a minimum item height
            self.lcount = len(self.lines)
        return self.h

    def truncate(self, remainder, report):
        """Return a copy of the section up to page break."""

        # Special case 1: Entire section will fit on page
        if self.get_h(report) <= (remainder + report.page_overflow):
            return (self, None)

        # Special case 2: Not enough space for minimum content
        chk = bullet_text()
        chk.heading = self.heading
        chk.subheading = self.subheading
        chk.lines = self.lines[0:1]	# minimum one item before break
        if chk.get_h(report) > remainder:
            # move entire section onto next page
            return (pagebreak(), self)

        # Standard case - section crosses page break, determines
        # ret: content on current page
        # rem: content on subsequent pages
        ret = bullet_text()
        rem = bullet_text()
        ret.heading = self.heading
        ret.subheading = self.subheading
        rem.heading = self.heading
        rem.subheading = self.subheading
        ret.footer = self.footer
        rem.footer = self.footer
        if rem.heading is not None:
            if rem.heading.rfind('(continued)') < 0:
                rem.heading += ' (continued)'
        ret.bullet = self.bullet
        rem.bullet = self.bullet
        seclines = len(self.lines)
        count = 0
        if seclines > 0:
            ret.lines.append(self.lines[0])
            count = 1 # case: min one line before break
        while count < seclines: 	# visit every item
            if ret.get_h(report) > remainder:
                # if overflow, undo last item and fall out to remainder
                rem.lines.append(ret.lines.pop(-1))
                break
            elif seclines - count <= 1:	
                break	# hanging item check (rm=1)
            ret.lines.append(self.lines[count])
            count += 1
        while count < seclines:
            # collect all remainder items in rem
            rem.lines.append(self.lines[count])
            count += 1
        return(ret, rem)

    def draw_pdf(self, report):
        """Output the bullet list to page."""
        report.c.save()
        if self.heading is not None:
            report.text_cent(report.midpagew, report.h, self.heading,
                           report.fonts['section'])
            report.h += report.section_height
        if self.subheading is not None:
            report.text_cent(report.midpagew, report.h, self.subheading,
                           report.fonts['subhead'])
            report.h += report.line_height
        if len(self.lines) > 0:
            if self.width is None:	# override by caller allowed
                self.width = report.body_width - mm2pt(15+10)
            for l  in self.lines:
                bstr = self.bullet
                if l[0] is not None:
                    bstr = l[0]		# allow override even with ''
                # draw bullet
                bh = report.line_height	# minimum item height is one line
                if bstr:
                    report.text_left(report.body_left+mm2pt(5.0), report.h,
                                     bstr, report.fonts['body'])
                # draw para
                ph = 0
                if l[1]:	# allow empty list item
                    (pw,ph) = report.text_para(report.body_left+mm2pt(15.0),
                                             report.h, l[1],
                                             report.fonts['body'], self.width)
                report.h += max(ph, bh)
        if self.footer:
            report.text_cent(report.midpagew, report.h, self.footer,
                              report.fonts['subhead'])
            report.h += report.line_height
        report.c.restore()

    def draw_xls(self, report, worksheet):
        """Output program element to excel worksheet."""
        row = report.h
        if self.heading:
            worksheet.write(row, 2, self.heading.strip(), XS_TITLE)
            row += 1
        if self.subheading:
            worksheet.write(row, 2, self.subheading.strip(), XS_SUBTITLE)
            row += 2
        else:
            row += 1
        if len(self.lines) > 0:
            for l in self.lines:
                oft = 0
                bstr = self.bullet
                if l[0]:
                    bstr = l[0]
                worksheet.write(row, 1, bstr, XS_LEFT)	# always one bullet
                istr = ''
                if l[1]: 
                    istr = l[1]
                for line in istr.split('\n'):
                    worksheet.write(row + oft, 2, line, XS_LEFT)
                    oft += 1
                row += max(oft, 1)
            row += 1
        report.h = row
        return None

    def draw_text(self, report, f, xtn):
        """Write out a section in markdown."""
        if self.heading:
            f.write(htlib.h3(htlib.escapetext(self.heading.strip())) + '\n\n')
        if self.subheading:
            f.write(htlib.p(htlib.escapetext(self.subheading.strip()),
                            {'class':'lead'}) + '\n\n')
        if len(self.lines) > 0:
            ol = []
            for l in self.lines:
                bstr = ''
                if l[0]:
                    bstr = '('+l[0]+') '
                if l[1]: 
                    bstr += l[1]
                ol.append(htlib.li(bstr.rstrip()))
            f.write(htlib.ul(ol))
            f.write('\n\n')

class preformat_text(object):
    """Block of pre-formatted/monospaced plain text."""
    def __init__(self, secid=None):
        self.sectionid = secid
        self.status = None
        self.heading = None	# scalar
        self.subheading = None	# scalar
        self.colheader = None	# scalar
        self.footer = None
        self.units = None
        self.lines = []		# list of scalars
        self.lcount = 0		# last count of lines/len
        self.h = None		# computed height on page

    def serialize(self, rep, sectionid=None):
        """Return a serializable map for JSON export."""
        ret = {}
        ret['sectionid'] = sectionid
        ret['type'] = 'pretext'
        ret['heading'] = self.heading
        ret['status'] = self.status
        ret['subheading'] = self.subheading
        ret['colheader'] = self.colheader
        ret['footer'] = self.footer
        ret['units'] = self.units
        ret['lines'] = self.lines
        ret['height'] = self.get_h(rep)
        ret['count'] = self.lcount
        return ret

    def get_h(self, report):
        """Return total height on page of section on report."""
        if self.h is None or len(self.lines) != self.lcount:
            cvec = self.lines[0:]
            if self.colheader:	# colheader is written out with body
                cvec.append(self.colheader)
            self.h = report.preformat_height(cvec)
            if self.heading:
                self.h += report.section_height
            if self.subheading:
                self.h += report.line_height
            self.lcount = len(self.lines)
        return self.h

    def truncate(self, remainder, report):
        """Return a copy of the section up to page break."""

        # Special case 1: Entire section will fit on page
        if self.get_h(report) <= (remainder + report.page_overflow):
            return (self, None)

        # Special case 2: Not enough space for minimum content
        chk = preformat_text()
        chk.heading = self.heading
        chk.subheading = self.subheading
        chk.colheader = self.colheader
        if len(self.lines) == 3: # special case, keep 'threes' together
            chk.lines = self.lines[0:]
        else:
            chk.lines = self.lines[0:2]
        if chk.get_h(report) > remainder:
            # move entire section onto next page
            return (pagebreak(), self)

        # Standard case - section crosses page break, determines
        # ret: content on current page
        # rem: content on subsequent pages
        ret = preformat_text()
        rem = preformat_text()
        ret.heading = self.heading
        ret.subheading = self.subheading
        rem.heading = self.heading
        rem.subheading = self.subheading
        if rem.heading is not None:
            if rem.heading.rfind('(continued)') < 0:
                rem.heading += ' (continued)'
        ret.colheader = self.colheader
        rem.colheader = self.colheader
        seclines = len(self.lines)
        count = 0
        if seclines > 0:
            ret.lines.append(self.lines[0])
            count = 1 # case: 3 lines broken on first line
        while count < seclines: # case: push min two lines over break
            if ret.get_h(report) > remainder:
                # pop last line onto rem and break
                rem.lines.append(ret.lines.pop(-1))
                break
            elif seclines - count <= 2: # push min 2 lines over to next page
                break
            ret.lines.append(self.lines[count])
            count += 1
        while count < seclines:
            rem.lines.append(self.lines[count])
            count += 1
        return(ret, rem)

    def draw_pdf(self, report):
        """Output a single section to the page."""
        report.c.save()
        if self.heading is not None:
            report.text_cent(report.midpagew, report.h, self.heading,
                           report.fonts['section'])
            report.h += report.section_height
        if self.subheading is not None:
            report.text_cent(report.midpagew, report.h, self.subheading,
                           report.fonts['subhead'])
            report.h += report.line_height
        if len(self.lines) > 0:
            rows = []
            if self.colheader:
                rows.append(self.colheader)
            rows.extend(self.lines)
            ust = '\n'.join(rows)
            (w, h) = report.text_cent(report.midpagew, report.h, ust,
                               report.fonts['monospace'],
                               halign=Pango.Alignment.LEFT)
            report.h += h
        report.c.restore()

    def draw_xls(self, report, worksheet):
        """Output program element to excel worksheet."""
        row = report.h
        if self.heading:
            worksheet.write(row, 2, self.heading.strip(), XS_TITLE)
            row += 1
        if self.subheading:
            worksheet.write(row, 2, self.subheading.strip(), XS_SUBTITLE)
            row += 2
        else:
            row += 1
        if len(self.lines) > 0:
            if self.colheader:
                worksheet.write(row, 2, self.colheader, XS_MONOSPACE)
                row += 1
            for l in self.lines:
                worksheet.write(row, 2, l.rstrip(), XS_MONOSPACE)
                row += 1
            row += 1
        report.h = row
        return None

    def draw_text(self, report, f, xtn):
        """Write out a section in markdown."""
        if self.heading:
            f.write(htlib.h3(htlib.escapetext(self.heading.strip())) + '\n\n')
        if self.subheading:
            f.write(htlib.p(htlib.escapetext(self.subheading.strip()), 
                            {'class':'lead'}) + '\n\n')
        if len(self.lines) > 0:
            ptxt = ''
            if self.colheader:
                ptxt += htlib.escapetext( self.colheader.rstrip()) + '\n'
            for row in self.lines:
                ptxt += htlib.escapetext(row.rstrip() + '\n')
            f.write(htlib.pre(ptxt) + '\n\n')

class event_index(object):
    """Copy of plain section, but in text output text links."""
    def __init__(self, secid=None):
        self.sectionid = secid
        self.status = None
        self.heading = None		# scalar
        self.colheader = None		# scalar
        self.subheading = None		# scalar
        self.footer = None
        self.units = None		# scalar
        self.lines = []			# list of column lists
        self.lcount = 0			
        self.h = None

    def serialize(self, rep, sectionid=None):
        """Return a serializable map for JSON export."""
        ret = {}
        ret['sectionid'] = sectionid
        ret['type'] = 'eventindex'
        ret['heading'] = self.heading
        ret['status'] = self.status
        ret['subheading'] = self.subheading
        ret['colheader'] = self.colheader
        ret['footer'] = self.footer
        ret['units'] = self.units
        ret['lines'] = self.lines
        ret['height'] = self.get_h(rep)
        ret['count'] = self.lcount
        return ret

    def get_h(self, report):
        """Return total height on page of section on report."""
        if self.h is None or len(self.lines) != self.lcount:
            # quick hack to get json export with no pdf ok
            self.h = report.line_height * len(self.lines)
            if self.colheader:	# colheader is written out with body
                self.h += report.line_height
                cvec.append(['-','-','-','-','-','-'])
            if self.heading:
                self.h += report.section_height
            if self.subheading:
                self.h += report.line_height
            self.lcount = len(self.lines)
        return self.h

    def truncate(self, remainder, report):
        """Return a copy of the section up to page break."""

        # Special case 1: Entire section will fit on page
        if self.get_h(report) <= (remainder + report.page_overflow):
            return (self, None)

        # Special case 2: Not enough space for minimum content
        chk = event_index()
        chk.heading = self.heading
        chk.subheading = self.subheading
        chk.colheader = self.colheader
        chk.units = self.units
        if len(self.lines) == 3: # special case, keep 'threes' together
            chk.lines = self.lines[0:]
        else:
            chk.lines = self.lines[0:2]
        if chk.get_h(report) > remainder:
            # move entire section onto next page
            return (pagebreak(), self)

        # Standard case - section crosses page break, determines
        # ret: content on current page
        # rem: content on subsequent pages
        ret = event_index()
        rem = event_index()
        ret.heading = self.heading
        ret.subheading = self.subheading
        rem.heading = self.heading
        rem.subheading = self.subheading
        if rem.heading is not None:
            if rem.heading.rfind('(continued)') < 0:
                rem.heading += ' (continued)'
        ret.colheader = self.colheader
        rem.colheader = self.colheader
        ret.units = self.units
        rem.units = self.units
        seclines = len(self.lines)
        count = 0
        if seclines > 0:
            ret.lines.append(self.lines[0])
            count = 1 # case: 3 lines broken on first line
        while count < seclines: # case: push min two lines over break
            if ret.get_h(report) > remainder:
                # pop last line onto rem and break
                rem.lines.append(ret.lines.pop(-1))
                break
            elif seclines - count <= 2: # push min 2 lines over to next page
                break
            ret.lines.append(self.lines[count])
            count += 1
        while count < seclines:
            rem.lines.append(self.lines[count])
            count += 1
        return(ret, rem)

    def draw_pdf(self, report):
        """Output a single section to the page."""
        report.c.save()
        if self.heading:
            report.text_cent(report.midpagew, report.h, self.heading,
                           report.fonts['section'])
            report.h += report.section_height
        if self.subheading:
            report.text_cent(report.midpagew, report.h, self.subheading,
                           report.fonts['subhead'])
            report.h += report.line_height
        if len(self.lines) > 0:
            rows = []
            if self.colheader:
                rows.append(self.colheader)
            rows.extend(self.lines)
            # just hard-code cols for now, later do a colspec?
            if self.units:
                ust = self.units
                if self.colheader:
                    ust = '\n'+ust 
                report.text_left(report.col_oft_units, report.h, ust,
                               report.fonts['body'])
            report.output_column(rows, 0, 'l', report.col_oft_rank)
            #report.output_column(rows, 1, u'r', report.col_oft_no)
            new_h = report.output_column(rows, 2, 'l', report.col_oft_name)
            report.output_column(rows, 3, 'l', report.col_oft_cat)
            #report.output_column(rows, 4, u'r', report.col_oft_time)
            #report.output_column(rows, 5, u'r', report.col_oft_xtra)
            report.h += new_h
        report.c.restore()

    def draw_xls(self, report, worksheet):
        """Output program element to excel worksheet."""
        row = report.h
        if self.heading:
            worksheet.write(row, 2, self.heading.strip(), XS_TITLE)
            row += 1
        if self.subheading:
            worksheet.write(row, 2, self.subheading.strip(), XS_SUBTITLE)
            row += 2
        else:
            row += 1
        if len(self.lines) > 0:
            rows = []
            if self.colheader:
                rows.append(vecmapstr(self.colheader,7))
            for r in self.lines:
                nv = r[0:6]
                if len(nv) == 2:
                    nv = [nv[0], None, nv[1]]
                rows.append(vecmapstr(nv, 7))
            if self.units:
                if self.colheader:
                    rows[1][6] = self.units
                else:
                    rows[0][6] = self.units
            for l in rows:
                # todo: apply styles to whole doc?
                worksheet.write(row, 0, l[0], XS_LEFT)
                #worksheet.write(row, 1, l[1], XS_RIGHT)
                worksheet.write(row, 2, l[2], XS_LEFT)
                worksheet.write(row, 3, l[3], XS_LEFT)
                #worksheet.write(row, 4, l[4], XS_RIGHT)
                #worksheet.write(row, 5, l[5], XS_RIGHT)
                #worksheet.write(row, 6, l[6], XS_LEFT)
                row += 1
            row += 1
        report.h = row
        return None

    def draw_text(self, report, f, xtn):
        """Write out a section in markdown."""
        if self.heading:
            f.write(htlib.h3(htlib.escapetext(self.heading.strip())) + '\n\n')
        if self.subheading:
            f.write(htlib.p(htlib.escapetext(self.subheading.strip()), 
                            {'class':'lead'}) + '\n\n')

        if len(self.lines) > 0:
            hdr = ''
            if self.colheader:
                pass	# !! ERROR?
                #hdr = htlib.thead(vec2htmllinkhead(self.colheader))
            rows = []
            for r in self.lines:
                nv = r[0:6]
                if len(nv) == 2:
                    nv = [nv[0], None, nv[1]]
                rows.append(nv)
            if self.units:
                rows[0].append(self.units)
            trows = []
            for l in rows:
                trows.append(vec2htmllinkrow(l, xtn))
            f.write(htlib.table([hdr, htlib.tbody(trows)],
                  {'class':'table table-striped table-condensed',
                   'style':'width: auto'}))
            f.write('\n\n')
        return None

class judge24rep(object):
    def __init__(self, secid=None):
        self.sectionid = secid
        self.heading = None
        self.status = None
        self.subheading = None
        self.colheader = None
        self.units = None
        self.footer = None
        self.lines = []
        self.lcount = 0
        self.h = None
        self.start = None
        self.finish = None
        self.laptimes = None

    def serialize(self, rep, sectionid=None):
        """Return a serializable map for JSON export."""
        ret = {}
        ret['sectionid'] = sectionid
        ret['type'] = 'section'
        ret['heading'] = self.heading
        ret['status'] = self.status
        ret['subheading'] = self.subheading
        ret['colheader'] = self.colheader
        ret['footer'] = self.footer
        ret['units'] = self.units
        ret['lines'] = self.lines
        ret['height'] = self.get_h(rep)
        ret['count'] = self.lcount
        return ret

    def get_h(self, report):
        """Return total height on page of section on report."""
        if self.h is None or len(self.lines) != self.lcount:
            self.lcount = len(self.lines)
            self.h = report.line_height * self.lcount
            if self.colheader:	# colheader is written out with body
                self.h += report.line_height
            if self.heading:
                self.h += report.section_height
            if self.subheading:
                self.h += report.line_height
            if self.footer:
                self.h += report.line_height
        return self.h

    def truncate(self, remainder, report):
        """Return a copy of the section up to page break."""

        # Special case 1: Entire section will fit on page
        if self.get_h(report) <= (remainder + report.page_overflow):
            return (self, None)

        # Special case 2: Not enough space for minimum content
        chk = judge24rep()
        chk.heading = self.heading
        chk.subheading = self.subheading
        chk.colheader = self.colheader
        chk.footer = self.footer
        chk.units = self.units
        chk.start = self.start
        chk.finish = self.finish
        chk.laptimes = self.laptimes
        if len(self.lines) <= 4: # special case, keep four or less together
            chk.lines = self.lines[0:]
        else:			 # BUT, don't break before third rider
            chk.lines = self.lines[0:2]
        if chk.get_h(report) > remainder:
            # move entire section onto next page
            return (pagebreak(), self)

        # Standard case - section crosses page break, determines
        # ret: content on current page
        # rem: content on subsequent pages
        ret = judge24rep()
        rem = judge24rep()
        ret.heading = self.heading
        ret.subheading = self.subheading
        ret.colheader = self.colheader
        ret.footer = self.footer
        ret.units = self.units
        ret.start = self.start
        ret.finish = self.finish
        ret.laptimes = self.laptimes
        rem.heading = self.heading
        rem.subheading = self.subheading
        rem.colheader = self.colheader
        rem.footer = self.footer
        rem.units = self.units
        rem.start = self.start
        rem.finish = self.finish
        rem.laptimes = self.laptimes
        if rem.heading is not None:
            if rem.heading.rfind('(continued)') < 0:
                rem.heading += ' (continued)'
        seclines = len(self.lines)
        count = 0
        if seclines > 0:
            while count < seclines and count < 3: # don't break until 3rd
                ret.lines.append(self.lines[count])
                count += 1
        while count < seclines:
            if ret.get_h(report) > remainder:
                # pop last line onto rem and break
                rem.lines.append(ret.lines.pop(-1))
                break
            elif seclines - count <= 2: # push min 2 names over to next page
                break
            ret.lines.append(self.lines[count])
            count += 1
        while count < seclines:
            rem.lines.append(self.lines[count])
            count += 1
        return(ret, rem)

    def draw_pdf(self, report):
        """Output a single section to the page."""
        report.c.save()
        if self.heading:
            report.text_cent(report.midpagew, report.h, self.heading,
                           report.fonts['section'])
            report.h += report.section_height
        if self.subheading:
            report.text_cent(report.midpagew, report.h, self.subheading,
                           report.fonts['subhead'])
            report.h += report.line_height
        cnt = 0
        if len(self.lines) > 0:
            if self.colheader:
                report.h += report.judges_row(report.h, self.colheader)
            sh = report.h
            if self.units:
                report.text_left(report.col_oft_units, report.h, self.units,
                               report.fonts['body'])
            stof = None
            for r in self.lines:
                if len(r) > 6 and r[6] is not None and len(r[6]) > 0 and self.start is not None and self.finish is not None:
                    stof = self.start
                    if len(r) > 9 and r[9] is not None:
                        stof += r[9]
                    report.laplines24(report.h, r[6], stof, self.finish)
                report.h += report.judges_row(report.h, r, cnt%2)
                #report.h += report.standard_row(report.h, r, cnt%2)
                cnt += 1
            eh = report.h	# - for the column shade box
            if stof is not None and self.laptimes is not None and len(self.laptimes) > 0:
                report.laplines24(sh, self.laptimes, stof, self.finish,
                                    endh=eh, reverse=True)
            report.drawbox(report.col_oft_time-mm2pt(15.0), sh,
                           report.col_oft_time+mm2pt(1.0), eh, 0.07)
        if self.footer:
            report.text_cent(report.midpagew, report.h, self.footer,
                              report.fonts['subhead'])
            report.h += report.line_height
        report.c.restore()

    def draw_xls(self, report, worksheet):
        """Output program element to excel worksheet."""
        row = report.h
        if self.heading:
            worksheet.write(row, 2, self.heading.strip(), XS_TITLE)
            row += 1
        if self.subheading:
            worksheet.write(row, 2, self.subheading.strip(), XS_SUBTITLE)
            row += 2
        else:
            row += 1
        if len(self.lines) > 0:
            rows = []
            if self.colheader:
                rows.append(vecmapstr(self.colheader,7))
            for r in self.lines:
                nv = r[0:6]
                if len(nv) == 2:
                    nv = [nv[0], None, nv[1]]
                ol = vecmapstr(nv, 7)
                #if len(r) > 6 and r[6]:
                    #ol[7] = r[6]
                rows.append(ol)
            if self.units:
                if self.colheader:
                    rows[1][6] = self.units
                else:
                    rows[0][6] = self.units
            for l in rows:
                # todo: apply styles to whole doc?
                worksheet.write(row, 0, l[0], XS_LEFT)
                worksheet.write(row, 1, l[1], XS_RIGHT)
                worksheet.write(row, 2, l[2], XS_LEFT)
                worksheet.write(row, 3, l[3], XS_LEFT)
                worksheet.write(row, 4, l[4], XS_RIGHT)
                worksheet.write(row, 5, l[5], XS_RIGHT)
                worksheet.write(row, 6, l[6], XS_LEFT)
                #of = 7
                #if 7 in l:
                  #st = self.start
                  #for lt in l[7][1:]:
                    #worksheet.write(row, of, (lt-st).rawtime(1), XS_RIGHT)
                    #of += 1
                    #st = lt
                row += 1
            row += 1
        if self.footer:
            worksheet.write(row, 2, self.footer.strip(), XS_SUBTITLE)
            row += 2
        report.h = row
        return None

    def draw_text(self, report, f, xtn):
        """Write out a section in markdown."""
        if self.heading:
            f.write(htlib.h3(htlib.escapetext(self.heading.strip())) + '\n\n') 
        if self.subheading:
            f.write(htlib.p(htlib.escapetext(self.subheading.strip()), 
                            {'class':'lead'}) + '\n\n')

        if len(self.lines) > 0:
            hdr = ''
            if self.colheader:
                hdr = htlib.thead(vec2htmlhead(self.colheader[0:6]))
            rows = []
            for r in self.lines:
                nv = r[0:6]
                if len(nv) == 2:
                    nv = [nv[0], None, nv[1]]
                rows.append(nv)
            if self.units:
                rows[0].append(self.units)
            trows = []
            for l in rows:
                trows.append(vec2htmlrow(l))
            f.write(htlib.table([hdr, htlib.tbody(trows)],
                  {'class':'table table-striped table-condensed',
                   'style':'width: auto'}))
            f.write('\n\n')
        if self.footer:
            f.write(self.footer.strip() + '\n\n')
        return None

class judgerep(object):
    def __init__(self, secid=None):
        self.sectionid = secid
        self.heading = None
        self.status = None
        self.subheading = None
        self.colheader = None
        self.units = None
        self.footer = None
        self.lines = []
        self.lcount = 0
        self.h = None
        self.start = None
        self.finish = None
        self.laptimes = None

    def serialize(self, rep, sectionid=None):
        """Return a serializable map for JSON export."""
        ret = {}
        ret['sectionid'] = sectionid
        ret['type'] = 'section'
        ret['heading'] = self.heading
        ret['status'] = self.status
        ret['subheading'] = self.subheading
        ret['colheader'] = self.colheader
        ret['footer'] = self.footer
        ret['units'] = self.units
        ret['lines'] = self.lines
        ret['height'] = self.get_h(rep)
        ret['count'] = self.lcount
        return ret

    def get_h(self, report):
        """Return total height on page of section on report."""
        if self.h is None or len(self.lines) != self.lcount:
            self.lcount = len(self.lines)
            self.h = report.line_height * self.lcount
            if self.colheader:	# colheader is written out with body
                self.h += report.line_height
            if self.heading:
                self.h += report.section_height
            if self.subheading:
                self.h += report.line_height
            if self.footer:
                self.h += report.line_height
        return self.h

    def truncate(self, remainder, report):
        """Return a copy of the section up to page break."""

        # Special case 1: Entire section will fit on page
        if self.get_h(report) <= (remainder + report.page_overflow):
            return (self, None)

        # Special case 2: Not enough space for minimum content
        chk = judgerep()
        chk.heading = self.heading
        chk.subheading = self.subheading
        chk.colheader = self.colheader
        chk.footer = self.footer
        chk.units = self.units
        chk.start = self.start
        chk.finish = self.finish
        chk.laptimes = self.laptimes
        if len(self.lines) <= 4: # special case, keep four or less together
            chk.lines = self.lines[0:]
        else:			 # BUT, don't break before third rider
            chk.lines = self.lines[0:2]
        if chk.get_h(report) > remainder:
            # move entire section onto next page
            return (pagebreak(), self)

        # Standard case - section crosses page break, determines
        # ret: content on current page
        # rem: content on subsequent pages
        ret = judgerep()
        rem = judgerep()
        ret.heading = self.heading
        ret.subheading = self.subheading
        ret.colheader = self.colheader
        ret.footer = self.footer
        ret.units = self.units
        ret.start = self.start
        ret.finish = self.finish
        ret.laptimes = self.laptimes
        rem.heading = self.heading
        rem.subheading = self.subheading
        rem.colheader = self.colheader
        rem.footer = self.footer
        rem.units = self.units
        rem.start = self.start
        rem.finish = self.finish
        rem.laptimes = self.laptimes
        if rem.heading is not None:
            if rem.heading.rfind('(continued)') < 0:
                rem.heading += ' (continued)'
        seclines = len(self.lines)
        count = 0
        if seclines > 0:
            while count < seclines and count < 3: # don't break until 3rd
                ret.lines.append(self.lines[count])
                count += 1
        while count < seclines:
            if ret.get_h(report) > remainder:
                # pop last line onto rem and break
                rem.lines.append(ret.lines.pop(-1))
                break
            elif seclines - count <= 2: # push min 2 names over to next page
                break
            ret.lines.append(self.lines[count])
            count += 1
        while count < seclines:
            rem.lines.append(self.lines[count])
            count += 1
        return(ret, rem)

    def draw_pdf(self, report):
        """Output a single section to the page."""
        report.c.save()
        if self.heading:
            report.text_cent(report.midpagew, report.h, self.heading,
                           report.fonts['section'])
            report.h += report.section_height
        if self.subheading:
            report.text_cent(report.midpagew, report.h, self.subheading,
                           report.fonts['subhead'])
            report.h += report.line_height
        cnt = 0
        if len(self.lines) > 0:
            if self.colheader:
                report.h += report.judges_row(report.h, self.colheader)
            sh = report.h
            if self.units:
                report.text_left(report.col_oft_units, report.h, self.units,
                               report.fonts['body'])
            stof = None
            for r in self.lines:
                if len(r) > 6 and r[6] is not None and len(r[6]) > 0 and self.start is not None and self.finish is not None:
                    stof = self.start
                    if len(r) > 9 and r[9] is not None:
                        stof += r[9]
                    report.laplines(report.h, r[6], stof, self.finish)
                report.h += report.judges_row(report.h, r, cnt%2)
                #report.h += report.standard_row(report.h, r, cnt%2)
                cnt += 1
            eh = report.h	# - for the column shade box
            if stof is not None and self.laptimes is not None and len(self.laptimes) > 0:
                report.laplines(sh, self.laptimes, stof, self.finish,
                                    endh=eh, reverse=True)
            report.drawbox(report.col_oft_time-mm2pt(15.0), sh,
                           report.col_oft_time+mm2pt(1.0), eh, 0.07)
        if self.footer:
            report.text_cent(report.midpagew, report.h, self.footer,
                              report.fonts['subhead'])
            report.h += report.line_height
        report.c.restore()

    def draw_xls(self, report, worksheet):
        """Output program element to excel worksheet."""
        row = report.h
        if self.heading:
            worksheet.write(row, 2, self.heading.strip(), XS_TITLE)
            row += 1
        if self.subheading:
            worksheet.write(row, 2, self.subheading.strip(), XS_SUBTITLE)
            row += 2
        else:
            row += 1
        if len(self.lines) > 0:
            revoft = row
            rows = []
            if self.colheader:
                revoft += 1
                rows.append(vecmapstr(self.colheader,7))
            for r in self.lines:
                nv = r[0:7]
                if len(nv) == 2:
                    nv = [nv[0], None, nv[1]]
                rows.append(vecmapstr(nv, 7))
            if self.units:
                if self.colheader:
                    rows[1][6] = self.units
                else:
                    rows[0][6] = self.units
            for l in rows:
                # todo: apply styles to whole doc?
                worksheet.write(row, 0, l[0], XS_LEFT)
                worksheet.write(row, 1, l[1], XS_RIGHT)
                worksheet.write(row, 2, l[2], XS_LEFT)
                worksheet.write(row, 3, l[3], XS_LEFT)
                worksheet.write(row, 4, l[4], XS_RIGHT)
                worksheet.write(row, 5, l[5], XS_RIGHT)
                worksheet.write(row, 6, l[6], XS_LEFT)
                srow = row - revoft
                if srow >= 0:
                    srcl = self.lines[srow]
                    if len(srcl) > 6 and srcl[6] is not None and len(srcl[6]) > 0:
                        roft = 7
                        for k in srcl[6]:
                            worksheet.write(row, roft, k.rawtime(1), XS_RIGHT)
                            roft += 1
                row += 1
            row += 1
        if self.footer:
            worksheet.write(row, 2, self.footer.strip(), XS_SUBTITLE)
            row += 2
        report.h = row
        return None

    def draw_text(self, report, f, xtn):
        """Write out a section in markdown."""
        if self.heading:
            f.write(htlib.h3(htlib.escapetext(self.heading.strip())) + '\n\n') 
        if self.subheading:
            f.write(htlib.p(htlib.escapetext(self.subheading.strip()), 
                            {'class':'lead'}) + '\n\n')

        if len(self.lines) > 0:
            hdr = ''
            if self.colheader:
                hdr = htlib.thead(vec2htmlhead(self.colheader[0:6]))
            rows = []
            for r in self.lines:
                nv = r[0:6]
                if len(nv) == 2:
                    nv = [nv[0], None, nv[1]]
                rows.append(nv)
            if self.units:
                rows[0].append(self.units)
            trows = []
            for l in rows:
                trows.append(vec2htmlrow(l))
            f.write(htlib.table([hdr, htlib.tbody(trows)],
                  {'class':'table table-striped table-condensed',
                   'style':'width: auto'}))
            f.write('\n\n')
        if self.footer:
            f.write(self.footer.strip() + '\n\n')
        return None

class gamut(object):
    """Whole view of the entire tour - aka crossoff."""
    def __init__(self, secid=None):
        self.sectionid = secid
        self.heading = None
        self.status = None
        self.subheading = None
        self.colheader = None
        self.units = None
        self.footer = None
        self.lines = []
        self.cellmap = {}
        self.maxcol = 9		# depends on tour
        self.minaspect = 2.0	# minimum ratio to retain
        self.lcount = 0
        self.grey = True
        self.h = None

    def serialize(self, rep, sectionid=None):
        """Return a serializable map for JSON export."""
        ret = {}
        ret['sectionid'] = sectionid
        ret['type'] = 'section'
        ret['heading'] = self.heading
        ret['status'] = self.status
        ret['subheading'] = self.subheading
        ret['colheader'] = self.colheader
        ret['footer'] = self.footer
        ret['units'] = self.units
        ret['lines'] = self.lines
        ret['data'] = self.cellmap
        ret['height'] = self.get_h(rep)
        ret['count'] = self.lcount
        return ret

    def get_h(self, report):
        """Return total height on page of section on report."""
        if self.h is None or len(self.lines) != self.lcount:
            self.lcount = len(self.lines)
            self.h = report.body_len # section always fills page
        return self.h

    def truncate(self, remainder, report):
        """Move onto next page or raise exception."""
        if self.get_h(report) <= (remainder + report.page_overflow):
            return (self, None)
        else:
            if report.pagefrac() < FEPSILON:
                raise RuntimeWarning('Section ' + repr(self.heading)
                          + ' will not fit on a page and will not break.')
            # move entire section onto next page
            return (pagebreak(), self)

    def draw_pdf(self, report):
        """Output a single section to the page."""
        report.c.save()
        glen = self.h
        if self.heading:
            report.text_cent(report.midpagew, report.h, self.heading,
                           report.fonts['section'])
            report.h += report.section_height
            glen -= report.section_height
        if self.subheading:
            report.text_cent(report.midpagew, report.h, self.subheading,
                           report.fonts['subhead'])
            report.h += report.line_height
            glen -= report.section_height
        if self.footer:
            glen -= report.line_height

        if self.lcount > 0:
            # determine geometry
            lmargin = report.body_left + mm2pt(0.25)
            rmargin = report.body_right
            if self.maxcol < 6:		# increase margins for teams of 6
                lmargin += mm2pt(10.0)
                rmargin -= mm2pt(10.0)
            elif self.maxcol > 8:	# decrease margins for teams of 8
                lmargin -= mm2pt(10.0)
                rmargin += mm2pt(10.0)
            pwidth = rmargin - lmargin
            cwidth = pwidth / self.maxcol
            cheight = glen / self.lcount
            caspect = cwidth / cheight
            if caspect < self.minaspect:
                cheight = cwidth / self.minaspect
            ## determine the fontz
            fnsz = cheight * 0.35
            gfonts = {}
            gfonts['key'] = Pango.FontDescription(report.gamutstdfont + ' ' 
                                                   + str(fnsz))
            fnsz = cheight * 0.13
            gfonts['text'] = Pango.FontDescription(report.gamutobfont + ' ' 
                                                   + str(fnsz))
            fnsz = cheight * 0.20
            gfonts['gcline'] = Pango.FontDescription(report.gamutobfont + ' ' 
                                                   + str(fnsz))
            al = 0.04
            ad = 0.12
            alph = ad
            for l in self.lines:
                colof = lmargin
                for c in l:
                    if c:
                        cmap = None
                        if c in self.cellmap:
                            cmap = self.cellmap[c]
                        report.gamut_cell(report.h, colof, cheight, cwidth, 
                                          c, alph, gfonts, cmap)
                    colof += cwidth
                if alph == al:
                    alph = ad
                else:
                    alph = al
                report.h += cheight
        
	## divide up and then enforce aspect limits
	# min aspect = ~1.2
	# use a 0.5-1.0mm gap on each edge (r/b)
	# max height of 15.0mm
	# min height of ~9mm
	# max width of 31.5
	# min width of 19.8

        if self.footer:
            report.text_cent(report.midpagew, report.h, self.footer,
                              report.fonts['subhead'])
            report.h += report.line_height
        ## advance report.h to end of page
        report.c.restore()

    def draw_xls(self, report, worksheet):
        """Output program element to excel worksheet."""
        return None	# SKIP on xls
        row = report.h
        if self.heading:
            worksheet.write(row, 2, self.heading.strip(), XS_TITLE)
            row += 1
        if self.subheading:
            worksheet.write(row, 2, self.subheading.strip(), XS_SUBTITLE)
            row += 2
        else:
            row += 1
        if len(self.lines) > 0:
            pass
            ## TODO: output columnar representation of team members
        if self.footer:
            worksheet.write(row, 2, self.footer.strip(), XS_SUBTITLE)
            row += 2
        report.h = row
        return None

    def draw_text(self, report, f, xtn):
        """Write out a section in markdown."""
        return None	# Skip section on web output
        if self.heading:
            f.write(htlib.h3(htlib.escapetext(self.heading.strip())) + '\n\n') 
        if self.subheading:
            f.write(htlib.p(htlib.escapetext(self.subheading.strip()), 
                            {'class':'lead'}) + '\n\n')

        if len(self.lines) > 0:
            pass
            ## TODO: write out tabular or columnar rep of members
        if self.footer:
            f.write(self.footer.strip() + '\n\n')
        return None

class section(object):
    def __init__(self, secid=None):
        self.sectionid = secid
        self.heading = None
        self.status = None
        self.subheading = None
        self.colheader = None
        self.units = None
        self.footer = None
        self.lines = []
        self.lcount = 0
        self.grey = True
        self.h = None

    def serialize(self, rep, sectionid=None):
        """Return a serializable map for JSON export."""
        ret = {}
        ret['sectionid'] = sectionid
        ret['type'] = 'section'
        ret['heading'] = self.heading
        ret['status'] = self.status
        ret['subheading'] = self.subheading
        ret['colheader'] = self.colheader
        ret['footer'] = self.footer
        ret['units'] = self.units
        ret['lines'] = self.lines
        ret['height'] = self.get_h(rep)
        ret['count'] = self.lcount
        return ret

    def get_h(self, report):
        """Return total height on page of section on report."""
        if self.h is None or len(self.lines) != self.lcount:
            self.lcount = len(self.lines)
            for l in self.lines:
                if len(l) > 6 and l[6] and isinstance(l[6], list):
                    self.lcount+= 1
            self.h = report.line_height * self.lcount
            if self.colheader:	# colheader is written out with body
                self.h += report.line_height
            if self.heading:
                self.h += report.section_height
            if self.subheading:
                self.h += report.line_height
            if self.footer:
                self.h += report.line_height
        return self.h

    def truncate(self, remainder, report):
        """Return a copy of the section up to page break."""

        # Special case 1: Entire section will fit on page
        if self.get_h(report) <= (remainder + report.page_overflow):
            return (self, None)

        # Special case 2: Not enough space for minimum content
        chk = section()
        chk.heading = self.heading
        chk.subheading = self.subheading
        chk.colheader = self.colheader
        chk.footer = self.footer
        chk.units = self.units
        if len(self.lines) <= 4: # special case, keep four or less together
            chk.lines = self.lines[0:]
        else:			 # BUT, don't break before third rider
            chk.lines = self.lines[0:2]
        if chk.get_h(report) > remainder:
            # move entire section onto next page
            return (pagebreak(), self)

        # Standard case - section crosses page break, determines
        # ret: content on current page
        # rem: content on subsequent pages
        ret = section()
        rem = section()
        ret.heading = self.heading
        ret.subheading = self.subheading
        ret.colheader = self.colheader
        ret.footer = self.footer
        ret.units = self.units
        rem.heading = self.heading
        rem.subheading = self.subheading
        rem.colheader = self.colheader
        rem.footer = self.footer
        rem.units = self.units
        if rem.heading is not None:
            if rem.heading.rfind('(continued)') < 0:
                rem.heading += ' (continued)'
        seclines = len(self.lines)
        count = 0
        if seclines > 0:
            while count < seclines and count < 3: # don't break until 3rd
                ret.lines.append(self.lines[count])
                count += 1
        while count < seclines:
            if ret.get_h(report) > remainder:
                # pop last line onto rem and break
                rem.lines.append(ret.lines.pop(-1))
                break
            elif seclines - count <= 2: # push min 2 names over to next page
                break
            ret.lines.append(self.lines[count])
            count += 1
        while count < seclines:
            rem.lines.append(self.lines[count])
            count += 1
        return(ret, rem)

    def draw_pdf(self, report):
        """Output a single section to the page."""
        report.c.save()
        if self.heading:
            report.text_cent(report.midpagew, report.h, self.heading,
                           report.fonts['section'])
            report.h += report.section_height
        if self.subheading:
            report.text_cent(report.midpagew, report.h, self.subheading,
                           report.fonts['subhead'])
            report.h += report.line_height
        cnt = 0
        if len(self.lines) > 0:
            if self.colheader:
                report.h += report.standard_row(report.h, self.colheader)
            #sh = report.h
            if self.units:
                report.text_left(report.col_oft_units, report.h, self.units,
                               report.fonts['body'])
            for r in self.lines:
                if len(r) > 5:
                    if r[1] is not None and r[1].lower() == 'pilot':
                        pass #r[1] = u''
                    elif not (r[0] or r[1] or r[2] or r[3]):
                        cnt = 1	# empty row?
                    else:
                        cnt += 1
                else:
                    cnt = 1	# blank all 'empty' lines
                grey = 0
                if self.grey:
                    grey = (cnt+1)%2
                report.h += report.standard_row(report.h, r, grey)
                if len(r) > 6 and isinstance(r[6], list):
                    report.h += report.standard_row(report.h,r[6],grey)
            #eh = report.h	- for the column shade box
            #report.drawbox(report.col_oft_time-mm2pt(20.0), sh,
                           #report.col_oft_time+mm2pt(1.0), eh, 0.07)
        if self.footer:
            report.text_cent(report.midpagew, report.h, self.footer,
                              report.fonts['subhead'])
            report.h += report.line_height
        report.c.restore()

    def draw_xls(self, report, worksheet):
        """Output program element to excel worksheet."""
        row = report.h
        if self.heading:
            worksheet.write(row, 2, self.heading.strip(), XS_TITLE)
            row += 1
        if self.subheading:
            worksheet.write(row, 2, self.subheading.strip(), XS_SUBTITLE)
            row += 2
        else:
            row += 1
        if len(self.lines) > 0:
            rows = []
            if self.colheader:
                rows.append(vecmapstr(self.colheader,7))
            for r in self.lines:
                nv = r[0:6]
                if len(nv) == 2:
                    nv = [nv[0], None, nv[1]]
                rows.append(vecmapstr(nv, 7))
                if len(r) > 6 and isinstance(r[6], list):
                    if r[6]:
                        nv = r[6]
                        rows.append(vecmapstr(nv, 7))
            if self.units:
                if self.colheader:
                    rows[1][6] = self.units
                else:
                    rows[0][6] = self.units
            for l in rows:
                # todo: apply styles to whole doc?
                worksheet.write(row, 0, l[0], XS_LEFT)
                worksheet.write(row, 1, l[1], XS_RIGHT)
                worksheet.write(row, 2, l[2], XS_LEFT)
                worksheet.write(row, 3, l[3], XS_LEFT)
                worksheet.write(row, 4, l[4], XS_RIGHT)
                worksheet.write(row, 5, l[5], XS_RIGHT)
                worksheet.write(row, 6, l[6], XS_LEFT)
                row += 1
            row += 1
        if self.footer:
            worksheet.write(row, 2, self.footer.strip(), XS_SUBTITLE)
            row += 2
        report.h = row
        return None

    def draw_text(self, report, f, xtn):
        """Write out a section in markdown."""
        if self.heading:
            f.write(htlib.h3(htlib.escapetext(self.heading.strip())) + '\n\n') 
        if self.subheading:
            f.write(htlib.p(htlib.escapetext(self.subheading.strip()), 
                            {'class':'lead'}) + '\n\n')

        if len(self.lines) > 0:
            hdr = ''
            if self.colheader:
                hdr = htlib.thead(vec2htmlhead(self.colheader[0:6]))
            rows = []
            for r in self.lines:
                nv = r[0:6]
                if len(nv) == 2:
                    nv = [nv[0], None, nv[1]]
                rows.append(nv)
                if len(r) > 6 and isinstance(r[6], list):
                    if r[6]:
                        rows.append(r[6])
            if self.units:
                rows[0].append(self.units)
            trows = []
            for l in rows:
                trows.append(vec2htmlrow(l))
            f.write(htlib.table([hdr, htlib.tbody(trows)],
                  {'class':'table table-striped table-condensed',
                   'style':'width: auto'}))
            f.write('\n\n')
        if self.footer:
            f.write(self.footer.strip() + '\n\n')
        return None

class pagebreak(object):
    """Dummy 'section' for page breaks."""
    def __init__(self, threshold=None):
        self.sectionid = 'break'
        self.threshold = threshold

    def serialize(self, rep, sectionid=None):
        """Return a serializable map for JSON export."""
        ret = {}
        ret['sectionid'] = sectionid
        ret['threshold'] = self.threshold
        ret['type'] = 'pagebreak'
        return ret

    def set_threshold(self, threshold):
        self.threshold = None
        try:
            nthresh = float(threshold)
            if nthresh > 0.05 and nthresh < 0.95:
                self.threshold = nthresh
        except:
            pass

    def get_threshold(self):
        return self.threshold

class image_elem(object):
    """Place an SVG image on the page."""
    def __init__(self, x1=None, y1=None, x2=None, y2=None,
                        halign=None, valign=None, source=None):
        if halign is None:
            halign = 0.5
        if valign is None:
            valign = 0.5
        self.x1 = x1
        self.x2 = x2
        self.y1 = y1
        self.y2 = y2
        self.halign = halign
        self.valign = valign
        self.xof = 0.0
        self.yof = 0.0
        self.sf = 1.0
        self.set_source(source)

    def set_source(self, source=None):
        self.source = source
        if self.source is not None:
            # Pre-compute geometry
            bw = self.x2 - self.x1
            bh = self.y2 - self.y1
            if math.fabs(bh) < 0.0001:	# avoid div zero
                bh += 1.0	# but normally an error?
            ab = bw / bh
            iw = float(self.source.props.width)
            ih = float(self.source.props.height)
            ai = iw / ih
            xoft = 0.0
            yoft = 0.0
            sf = 1.0
            if ai > ab:     # 'wider' than box, scale to box w
                # xoft will be 0 for all aligns
                sf = bw / iw
                yoft = self.valign * (bh - ih * sf)
            else:           # 'higher' than box, scale to box h
                # yoft will be 0 for all aligns
                sf = bh / ih
                xoft = self.halign * (bw - iw * sf)
            self.sf = sf
            self.xof = self.x1 + xoft
            self.yof = self.y1 + yoft

    def draw(self, c):
        if self.source is not None:
            c.save()
            c.translate(self.xof, self.yof)
            c.scale(self.sf, self.sf)
            self.source.render_cairo(c)
            c.restore()

class arc_elem(object):
    """Pace an optionally shaded arc on the page."""
    def __init__(self, cx=None, cy=None, r=None, a1=None, a2=None, 
                       fill=None, width=None, colour=None, dash=None):
        self.cx = cx
        self.cy = cy
        self.r = r
        self.a1 = a1
        self.a2 = a2
        self.fill = fill
        self.width = width
        self.colour = colour
        self.dash = dash
    def draw(self, c):
        c.save()
        #c.move_to(self.cx, self.cy)
        c.new_sub_path()
        c.arc(self.cx, self.cy, self.r, self.a1, self.a2)
        outline = False
        if self.width is not None:
            outline = True
            c.set_line_width(self.width)
        if self.fill is not None:
            c.set_source_rgb(self.fill[0], self.fill[1], self.fill[2])
            if outline:
                c.fill_preserve()
            else:
                c.fill()
        if outline:
            if self.colour is not None:
                c.set_source_rgb(self.colour[0], self.colour[1], self.colour[2])
            if self.dash is not None:
                c.set_dash(self.dash)
            c.stroke()
        c.restore()

class box_elem(object):
    """Place an optionally shaded box on the page."""
    def __init__(self, x1=None, y1=None, x2=None, y2=None, fill=None,
                        width=None, colour=None, dash=None):
        self.x1 = x1
        self.y1 = y1
        self.x2 = x2
        self.y2 = y2
        self.fill = fill
        self.width = width
        self.colour = colour
        self.dash = dash

    def draw(self, c):
        c.save()
        c.move_to(self.x1, self.y1)
        c.line_to(self.x2, self.y1)
        c.line_to(self.x2, self.y2)
        c.line_to(self.x1, self.y2)
        c.close_path()
        outline = False
        if self.width is not None:
            outline = True
            c.set_line_width(self.width)
        if self.fill is not None:
            c.set_source_rgb(self.fill[0], self.fill[1], self.fill[2])
            if outline:
                c.fill_preserve()
            else:
                c.fill()
        if outline:
            if self.colour is not None:
                c.set_source_rgb(self.colour[0], self.colour[1], self.colour[2])
            if self.dash is not None:
                c.set_dash(self.dash)
            c.stroke()
        c.restore()

class line_elem(object):
    """Places a line on the page."""
    def __init__(self, x1=None, y1=None, x2=None, y2=None,
                        width=None, colour=None, dash=None):
        self.x1 = x1
        self.y1 = y1
        self.x2 = x2
        self.y2 = y2
        self.width = width
        self.colour = colour
        self.dash = dash

    def draw(self, c):
        c.save()
        if self.width is not None:
            c.set_line_width(self.width)
        if self.colour is not None:
            c.set_source_rgb(self.colour[0], self.colour[1], self.colour[2])
        if self.dash is not None:
            c.set_dash(self.dash)
        c.move_to(self.x1, self.y1)
        c.line_to(self.x2, self.y2)
        c.stroke()
        c.restore()

class text_elem(object):
    """Places string of text on the page."""
    def __init__(self, x=None, y=None, align=None, font=None,
                        colour=None, source=None, report=None):
        self.x = x
        self.y = y
        self.align = align
        self.font = font
        self.colour = colour
        self.source = source
        self.report = report
    def draw(self, c):
        msg = None
        if self.source:
            if self.source in self.report.strings:
                if self.report.strings[self.source]:
                    msg = self.report.strings[self.source]
            else:
                msg = self.source
        if msg:
            c.save()
            l = PangoCairo.create_layout(c)
            if self.font is not None:
                l.set_font_description(self.font)
            if self.colour is not None:
                c.set_source_rgb(self.colour[0], self.colour[1], self.colour[2])
            l.set_text(msg, -1)
            (tw,th) = l.get_pixel_size()
            c.move_to(self.x-(self.align * tw), self.y)
            PangoCairo.update_layout(c, l)
            PangoCairo.show_layout(c, l)
            c.restore()

class group_elem(object):
    """Place each defined element on the page."""
    def __init__(self, report=None, elems=[]):
        self.report = report
        self.elems = elems
        self.indraw = False
    def draw(self, c):
        if self.indraw:
            return	# Ignore recursion
        self.indraw = True
        c.save()
        for e in self.elems:
            if e in self.report.elements:
                self.report.elements[e].draw(c)
        c.restore()
        self.indraw = False

class printrep(object):
    """Printed Report class."""
    def __init__(self, template=None):

        # load template	-> also declares page geometry variables
        self.html_template = ''
        self.coverpage = None
        self.loadconfig(template)

        # override timestamp
        self.strings['timestamp'] = (
                     str(datetime.date.today().strftime('%A, %B %d %Y '))
                     + tod.tod('now').meridian() )

        # Status and context values
        self.provisional = False
        self.reportstatus = None	# optional flag for virtual etc
        self.serialno = str(int(10.0*time.time())) # may be overidden
        self.eventid = None		# stage no or other identifier
        self.customlinks = []		# manual override links
        self.prevlink = None
        self.nextlink = None
        self.indexlink = None
        self.canonical = None
        self.pagemarks = False
        self.s = None
        self.c = None
        self.h = None		# position on page during write
        self.curpage = None	# current page in report
        self.sections = []	# source section data
        self.pages = []		# paginated sections

        # temporary col offset values...
        self.col_oft_rank = self.body_left		# left align
        self.col_oft_no = self.body_left + mm2pt(18)	# right align
        self.col_oft_name = self.body_left + mm2pt(19)	# left align
        self.col_oft_cat = self.body_right - mm2pt(62)	# ~left align
        self.col_oft_time = self.body_right - mm2pt(20)	# right align
        self.col_oft_xtra = self.body_right - mm2pt(2) # right align
        self.col_oft_units = self.body_right - mm2pt(1)	# left

    def reset_geometry(self, width=None, height=None,
                             sidemargin=None, endmargin=None,
                             printmargin=None):
        """Overwrite any new values and then compute page geometry."""
        if width is not None:
            self.pagew = width
        if height is not None:
            self.pageh = height
        if sidemargin is not None:
            self.sidemargin = sidemargin
        if endmargin is not None:
            self.endmargin = endmargin
        if printmargin is not None:
            self.printmargin = printmargin

        # compute midpage values
        self.midpagew = self.pagew / 2.0
        self.midpageh = self.pageh / 2.0

        # compute body region
        self.printh = self.pageh - self.printmargin - self.printmargin
        self.printw = self.pagew - self.printmargin - self.printmargin
        self.body_left = self.sidemargin
        self.body_right = self.pagew - self.sidemargin
        self.body_width = self.body_right - self.body_left
        self.body_top = self.endmargin
        self.body_bot = self.pageh - self.endmargin
        self.body_len = self.body_bot - self.body_top

    def loadconfig(self, filename=None):
        """Initialise the report template."""

        # Default page geometry
        self.pagew = 595.0
        self.pageh = 842.0
        self.sidemargin = mm2pt(25.5)
        self.endmargin = mm2pt(36.2)
        self.printmargin = mm2pt(5.0)
        self.minbreak = 0.75	# minimum page break threshold

        # Default empty template elements
        self.colours = {}
        self.colours['white'] = [1.0, 1.0, 1.0]
        self.colours['shade'] = [0.9, 0.9, 0.9]
        self.colours['black'] = [0.0, 0.0, 0.0]
        self.elements = {}
        self.fonts = {}
        self.fonts['body'] = Pango.FontDescription(BODYFONT)
        self.fonts['bodyoblique'] = Pango.FontDescription(BODYFONT)
        self.fonts['bodybold'] = Pango.FontDescription(BODYBOLDFONT)
        self.fonts['section'] = Pango.FontDescription(SECTIONFONT)
        self.fonts['subhead'] = Pango.FontDescription(SUBHEADFONT)
        self.fonts['monospace'] = Pango.FontDescription(MONOSPACEFONT)
        self.fonts['provisional'] = Pango.FontDescription(PROVFONT)
        self.fonts['title'] = Pango.FontDescription(TITLEFONT)
        self.fonts['subtitle'] = Pango.FontDescription(SUBTITLEFONT)
        self.fonts['annotation'] = Pango.FontDescription(ANNOTFONT)
        self.gamutstdfont = GAMUTSTDFONT
        self.gamutobfont = GAMUTOBFONT
        self.strings = {}
        self.images = {}
        self.header = []
        self.template = None
        self.page_elem = None

        # read in from template
        cr = jsonconfig.config()
        cr.add_section('page')
        cr.add_section('elements')
        cr.add_section('fonts')
        cr.add_section('strings')
        cr.add_section('colours')
        tfile = metarace.PDF_TEMPLATE_FILE
        if filename is not None:
            tfile = filename
        try:
            tfile = metarace.default_file(tfile)
            with open(tfile, encoding='utf-8', errors='ignore') as f:
                cr.read(f)
        except Exception as e:
            print(('Error reading print template: ' + repr(e)))

        # read in page options
        if cr.has_option('page', 'width'):
            self.pagew = str2len(cr.get('page', 'width'))
        if cr.has_option('page', 'height'):
            self.pageh = str2len(cr.get('page', 'height'))
        if cr.has_option('page', 'sidemargin'):
            self.sidemargin = str2len(cr.get('page', 'sidemargin'))
        if cr.has_option('page', 'endmargin'):
            self.endmargin = str2len(cr.get('page', 'endmargin'))
        if cr.has_option('page', 'printmargin'):
            self.printmargin = str2len(cr.get('page', 'printmargin'))
        if cr.has_option('page', 'minbreak'):
            self.minbreak = str2align(cr.get('page', 'minbreak'))
        self.section_height = SECTION_HEIGHT
        if cr.has_option('page', 'secheight'):
            self.section_height = str2len(cr.get('page', 'secheight'))
        self.line_height = LINE_HEIGHT
        if cr.has_option('page', 'lineheight'):
            self.line_height = str2len(cr.get('page', 'lineheight'))
        self.page_overflow = PAGE_OVERFLOW
        if cr.has_option('page', 'pageoverflow'):
            self.page_overflow = str2len(cr.get('page', 'pageoverflow'))
        self.twocol_width = TWOCOL_WIDTH
        if cr.has_option('page', 'twocolwidth'):
            self.twocol_width = str2len(cr.get('page', 'twocolwidth'))
        self.reset_geometry()
        if cr.has_option('page', 'elements'):
            self.header = cr.get('page', 'elements').split()
        if cr.has_option('page', 'coverpage'):
            self.coverpage =  image_elem(0.0, 0.0,
                                         self.pagew, self.pageh,
                                         0.5, 0.5,
                                         self.get_image(cr.get('page',
                                                        'coverpage')))

        # read in font declarations
        for s in cr.options('fonts'):
            if s == 'gamutstdfont':
                self.gamutstdfont = cr.get('fonts', s)
            elif s == 'gamutobfont':
                self.gamutobfont = cr.get('fonts', s)
            else:
                self.fonts[s] = Pango.FontDescription(cr.get('fonts', s))
        # read in string declarations
        for s in cr.options('strings'):
            self.strings[s] = cr.get('strings', s)
        # read in colours
        for s in cr.options('colours'):
            self.colours[s] = str2colour(cr.get('colours', s))
        # read in page elements
        for s in cr.options('elements'):
            elem = self.build_element(s, cr.get('elements', s))
            if elem is not None:
                self.elements[s] = elem
        # prepare the html wrapper
        if cr.has_option('page', 'html_template'):
            self.html_template = self.load_htmlfile(
                    cr.get('page', 'html_template'))
            if '__REPORT_CONTENT__' not in self.html_template:
                print('Error: Ignored invalid HTML template file.')
                self.html_template = htlib.emptypage()
        else:
            self.html_template = htlib.emptypage()

    def load_htmlfile(self, templatefile):
        """Pull in a html template if it exists."""
        ret = ''
        try:
            fname = metarace.default_file(templatefile)
            with open(fname, encoding='utf-8', errors='ignore') as f:
                ret = f.read()
        except:
            ret = ''
        return ret

    def load_csv(self, srcfile=None):
        """Read sections in from the provided csv file."""
        infile = metarace.default_file(srcfile)
        with open(infile, newline='') as f:
            cr = csv.reader(f)
            incols = None
            for r in cr:
                if len(r) > 0:
                    if incols is None:
                        # first row determines column structure
                        if csv_colkey(r[0]) in CSV_REPORT_COLUMNS:
                            incols = []
                            for col in r:
                                incols.append(csv_colkey(col))
                            continue	# consume first row
                        else:
                            incols = CSV_REPORT_DEFAULT_COLUMNS
                    # read in row
                    srec = {}
                    for i in range(0,len(incols)):
                        if len(r) > i:
                            val = r[i]
                            key = incols[i]
                            srec[key] = val
                    # create section
                    s = None
                    if srec['type'] in CSV_REPORT_SECTIONS:
                        s = CSV_REPORT_SECTIONS[srec['type']]()
                    else:
                        s = section()	# default is all-purpose list
                    doheader = False
                    if not isinstance(s, pagebreak):
                        if 'head' in srec and srec['head']:
                            s.heading = srec['head']
                        if 'subh' in srec and srec['subh']:
                            s.subheading = srec['subh']
                        if 'foot' in srec and srec['foot']:
                            s.footer = srec['foot']
                        if 'unit' in srec and srec['unit']:
                            s.units = srec['unit']
                        if 'colu' in srec and srec['colu']:
                            doheader = True
                        if 'sour' in srec and srec['sour']:
                            infile = metarace.default_file(srec['sour'])
                            with open(infile, newline='') as g:
                                cr = csv.reader(g)
                                for sr in cr:
                                    if doheader and s.colheader is None:
                                        if isinstance(s, preformat_text):
                                            s.colheader = sr[0]
                                        else:
                                            s.colheader = sr
                                    else:
                                        if isinstance(s, preformat_text):
                                            s.lines.append(sr[0])
                                        elif isinstance(s, (sprintround,
                                                         sprintfinal)):
                                            # ignore data for sprint rounds
                                            pass	# TODO for now
                                        else:
                                            s.lines.append(sr)

                    self.add_section(s)

    def set_font(self, key=None, val=None):
        if key:
            self.fonts[key] = Pango.FontDescription(val)

    def get_image(self, key=None):
        """Return an image handle or None."""
        ret = None
        if key is not None:
            if key not in self.images:
                fname = metarace.default_file(key + '.svg')
                fh = None
                if os.path.isfile(fname):
                    fh = Rsvg.Handle(fname)
                self.images[key] = fh
            ret = self.images[key]
        return ret

    def pagepoint(self, pstr, orient='x'):
        """Convert a positional string into an absolute page reference."""
        ret = 0.0
        ref = self.pagew
        mid = self.midpagew
        if orient == 'y':	# vertical orientation
            ref = self.pageh
            mid = self.midpageh

        # special cases - 'mid' and 'max'
        if pstr == 'mid':
            ret = mid
        elif pstr == 'max':
            ret = ref
        else:
            relpos = str2len(pstr)
            if relpos < 0.0:
                ret = ref + relpos	# relative to bottom/right
            else:
                ret = relpos		# relative to top/left
        return ret

    def add_element(self, ekey, estr):
        """Build the element and add it to the page."""
        if ekey not in self.header:
            self.header.append(ekey)
        if ekey in self.elements:
            del self.elements[ekey]
        elem = self.build_element(ekey, estr)
        if elem is not None:
            self.elements[ekey] = elem
        
    def build_element(self, ekey, estr):
        """Build the element and add it to the element map."""
        ret = None
        emap = vecmap(estr.split(','))
  
        etype = emap[0].lower()
        if etype == 'line':
            width = str2len(emap[5])
            colour = None
            if emap[6] and emap[6] in self.colours:
                colour = self.colours[emap[6]]
            dash = str2dash(emap[7])
            x1 = self.pagepoint(emap[1], 'x')
            y1 = self.pagepoint(emap[2], 'y')
            x2 = self.pagepoint(emap[3], 'x')
            y2 = self.pagepoint(emap[4], 'y')
            ret = line_elem(x1, y1, x2, y2,
                                            width, colour, dash)
        elif etype == 'image':
            x1 = self.pagepoint(emap[1], 'x')
            y1 = self.pagepoint(emap[2], 'y')
            x2 = self.pagepoint(emap[3], 'x')
            y2 = self.pagepoint(emap[4], 'y')
            halign = str2align(emap[5])
            valign = str2align(emap[6])
            source = self.get_image(emap[7])
            ret = image_elem(x1, y1, x2, y2,
                               halign, valign, source)
        elif etype == 'box':
            fill = None
            if emap[5] and emap[5] in self.colours:
                fill = self.colours[emap[5]]
            width = str2len(emap[6])
            colour = None
            if emap[7] and emap[7] in self.colours:
                colour = self.colours[emap[7]]
            dash = str2dash(emap[8])
            x1 = self.pagepoint(emap[1], 'x')
            y1 = self.pagepoint(emap[2], 'y')
            x2 = self.pagepoint(emap[3], 'x')
            y2 = self.pagepoint(emap[4], 'y')
            ret = box_elem(x1, y1, x2, y2, fill,
                               width, colour, dash)
        elif etype == 'arc':
            fill = None
            if emap[6] and emap[6] in self.colours:
                fill = self.colours[emap[6]]
            width = str2len(emap[7])
            colour = None
            if emap[8] and emap[8] in self.colours:
                colour = self.colours[emap[8]]
            dash = str2dash(emap[9])
            cx = self.pagepoint(emap[1], 'x')
            cy = self.pagepoint(emap[2], 'y')
            r = str2len(emap[3])
            a1 = str2angle(emap[4])
            a2 = str2angle(emap[5])
            ret = arc_elem(cx, cy, r, a1, a2, fill,
                               width, colour, dash)
        elif etype == 'text':
            x = self.pagepoint(emap[1], 'x')
            y = self.pagepoint(emap[2], 'y')
            align = str2align(emap[3])
            font = None
            if emap[4] and emap[4] in self.fonts:
                font = self.fonts[emap[4]]
            colour = None
            if emap[5] and emap[5] in self.colours:
                colour = self.colours[emap[5]]
            source = None
            if emap[6]:
                source = emap[6].strip()
            ret = text_elem(x, y, align, font, colour,
                                  source, self)
        elif etype == 'group':	# slightly special case
            elist = estr.split(',')[1:]
            glist = []
            for e in elist:
                e = e.strip()
                if e:
                    glist.append(e)	# preserve ordering
            ret = group_elem(self, glist)
        return ret

    def get_pages(self):
        return len(self.pages)

    def insert_section(self, sec, pos=0):
        self.sections.insert(pos, sec)

    def add_section(self, sec):
        self.sections.append(sec)

    def del_section(self, secid=None):
        """Crude section removal by section id component match."""
        if secid is None:
            return	# breakout
        cur = 0
        while len(self.sections) > cur:
            if secid in self.sections[cur].sectionid:
                del(self.sections[cur])
            else:
                cur += 1
            
    def set_provisional(self, flag=True):
        self.provisional = flag

    def set_pagemarks(self, flag=True):
        self.pagemarks = flag

    def output_json(self, file=None):
        """Output the JSON version."""
        if 'pagestr' in self.strings:
            del self.strings['pagestr']	# remove spurious string data
        ret = {'report':{}, 'sections':{}, 'api':'metarace.report',
               'apiversion':APIVERSION, 'libversion':metarace.VERSION}
        rep = ret['report']
        rep['provisional'] = self.provisional
        rep['reportstatus'] = self.reportstatus
        rep['eventid'] = self.eventid
        rep['serialno'] = self.serialno
        rep['prevlink'] = self.prevlink
        rep['nextlink'] = self.nextlink
        rep['indexlink'] = self.indexlink
        rep['canonical'] = self.canonical
        rep['strings'] = self.strings
        rep['sections'] = []
        secmap = ret['sections']
        for s in self.sections:
            secid = mksectionid(secmap, s.sectionid)
            secmap[secid] = s.serialize(self, secid)
            rep['sections'].append(secid)
        # serialise to the provided file handle
        json.dump(ret, file, indent=1, sort_keys=True)

    def output_xls(self, file=None):
        """Output xls spreadsheet."""
        return	 # TODO - translate to xlsxwrite as in cadel DR sample
        #wb = xlwt.Workbook()
        #sheetname = 'report'	# unicode ok here? defer to 3
        ## Docstring?
        #ws = wb.add_sheet(sheetname)
        ## column widths
        #ws.col(0).width = int(7*256)
        #ws.col(1).width = int(5*256)
        #ws.col(2).width = int(36*256)
        #ws.col(3).width = int(13*256)
        #ws.col(4).width = int(9*256)
        #ws.col(5).width = int(7*256)
        #ws.col(6).width = int(3*256)
        # 
        #title = ''
        #for s in ['title', 'subtitle']:
            #if s in self.strings and self.strings[s]:
                #title += self.strings[s] + ' '
        #ws.write(0,2,title.strip(),XS_TITLE)
        #self.h = 2	# Start of 'document'
        #for s in ['datestr', 'docstr', 'diststr', 'commstr', 'orgstr']:
            #if s in self.strings and self.strings[s]:
                #ws.write(self.h, 2, self.strings[s].strip(), XS_LEFT)
                #self.h += 1
        #self.h += 1
        #if self.provisional:
            #ws.write(self.h, 2, 'PROVISIONAL',
                     #XS_TITLE)
            #self.h += 2

        ## output all the sections...
        #for s in self.sections:
            #if not isinstance(s, pagebreak):
                #s.draw_xls(self, ws)	# call into section to draw
        # 
        #wb.save(file)

    def macrowrite(self, file=None, text=''):
        """Write text to file substituting macros in text."""
        titlestr = ''
        for s in ['title', 'subtitle']:
            if s in self.strings and self.strings[s]:
                titlestr += self.strings[s] + ' '
        ret = text.replace('__REPORT_TITLE__', titlestr.strip())
        for s in self.strings:
            mackey = '__' + s.upper().strip() + '__'
            if mackey in ret:
                ret = ret.replace(mackey, self.strings[s])
        file.write(ret)

    def output_html(self, file=None, linkbase='', linktypes=[]):
        """Output a html version of the report."""
        cw = file
        (top, sep, bot) = self.html_template.partition('__REPORT_CONTENT__')

        # macro output the first part of the template
        self.macrowrite(cw, top)

        # output the body of the post
        self.output_htmlintext(cw, linkbase, linktypes, '.html')

        # macro output the footer of the template
        self.macrowrite(cw, bot)

    def output_text(self, file=None, linkbase='', linktypes=[]):
        """Output a text version of the report."""
        cw = file
        # plain text header
        title = ''
        for s in ['title', 'subtitle']:
            if s in self.strings and self.strings[s]:
                title += self.strings[s] + ' '
        cw.write(title.strip())
        cw.write('\n\n')
        self.output_htmlintext(cw, linkbase, linktypes)

    def output_htmlintext(self, file=None, linkbase='', linktypes=[],
                                           htmlxtn=''):
        """Output the html in text report body."""
        cw = file
        navbar = ''
        for link in self.customlinks:	# to build custom toolbars
            navbar += htlib.a(
                       htlib.escapetext(link[0]),
                       {'href':link[1]+htmlxtn, 'class':'btn btn-default'})
        if self.prevlink:
            navbar += htlib.a(
                       htlib.escapetext('\u2190 Previous Event'),
                       {'href':self.prevlink+htmlxtn,
                        'class':'btn btn-default'})
        if self.indexlink:
            navbar += htlib.a(
                       htlib.escapetext('\u2191 Event Index'),
                       {'href':self.indexlink+htmlxtn,
                        'class':'btn btn-default'})
        if self.provisional:	# add refresh button
            pass
            #navbar += htlib.a(
                       #htlib.escapetext(u'Refresh \u21bb'),
                       #{u'href':u'#', u'class':u'btn btn-default',
                        #u'onclick':u'window.location.reload()'})
        if self.nextlink:
            navbar += htlib.a(
                       htlib.escapetext('Next Event \u2192'),
                       {'href':self.nextlink+htmlxtn,
                        'class':'btn btn-default'})
        if navbar:	# write out bar if non-empty
            cw.write(htlib.div(
                       htlib.div(
                         navbar,
                         {'class':'btn-group'}
                       ),
                       {'class':'btn-toolbar'}
                     )+'\n\n')

        if self.provisional:	 # add prov marker
            cw.write(htlib.span('Provisional',
                      {'id':'pgre', 'class':'label label-warning pull-right'})+'\n\n')
        metalist = []
        for s in ['datestr', 'docstr', 'diststr', 'commstr', 'orgstr']:
            if s in self.strings and self.strings[s]:
                metalist.append((ICONMAP[s],
                                 htlib.escapetext(self.strings[s].strip())))
        if len(linktypes) > 0:
            linkmsg = 'Download as:'
            for xtn in linktypes:
                xmsg = xtn
                if xtn in FILETYPES:
                    xmsg = FILETYPES[xtn]
                linkmsg += ' [' + htlib.a(xmsg,
                                   {'href':linkbase + '.' + xtn}) + ']'
            metalist.append((ICONMAP['download'], linkmsg))
        if len(metalist) > 0:
            itemstr = ''
            for li in metalist:
                itemstr += htlib.li([htlib.i('',{'class':li[0]}),li[1]])
            cw.write(htlib.div(htlib.ul(itemstr, {'class':'unstyled'}), 
                              {'class':'well'}) + '\n\n')
        # output a jump trigger...
        cw.write('<!-- Jumper:jump -->\n\n')

        # output all the sections...
        for s in self.sections:
            if not isinstance(s, pagebreak):
                s.draw_text(self, cw, htmlxtn)	# call into section

        cw.write('\n')

    def set_context(self, context):
        self.s = None
        self.c = context

    def start_gtkprint(self, context):
        """Prepare document for a gtkPrint output."""
        self.s = None
        self.c = context

        # break report into pages as required
        self.paginate()

        # special case - dangerous
        if len(self.pages) > 0 and len(self.pages[-1]) == 0:
            del self.pages[-1]

    def make_template(self):
        """Write the current template to a pattern."""
        # save current vars temp
        os = self.s
        oc = self.c

        # draw page template into a temporary surface
        self.s = cairo.PDFSurface(None, self.pagew, self.pageh)
        self.c = cairo.Context(self.s)
        for e in self.header:
            self.draw_element(e)
        self.s.flush()
        self.template = self.s	# save for re-use

        # restore 'env' vars
        self.s = os
        self.c = oc

    def output_pdf(self, file=None, docover=False):
        """Prepare document and then output to a PDF surface."""

        # create output cairo surface and save contexts
        self.s = cairo.PDFSurface(file, self.pagew, self.pageh)
        self.c = cairo.Context(self.s)

        # break report into pages as required
        self.paginate()
        # Special case: Do not allow trailing breaks to leave empty page
        #               on end of report
        if len(self.pages) > 0 and len(self.pages[-1]) == 0:
            del self.pages[-1]
        npages = self.get_pages()
        
        # if coverpage present, output
        if docover and self.coverpage is not None:
            self.draw_cover()
            self.c.show_page()	# start a new blank page

        # output each page
        for i in range(0, npages):
            self.draw_page(i)
            if i < npages - 1:
                self.c.show_page()	# start a new blank page

        # finalise surface - may be a blank pdf if no content
        self.s.flush()
        self.s.finish()

    def draw_element(self, elem):
        """Draw the named element if it is defined."""
        if elem in self.elements:
            self.elements[elem].draw(self.c)
        else:
            pass

    def draw_template(self):
        """Draw page layout."""
        #if self.template is None:
            #self.make_template()
        ## template surface approach wirtes out as bitmap in new cairo
        for e in self.header:
            self.draw_element(e)
        #self.c.save()
        #self.c.set_source_surface(self.template)
        #self.c.paint()
        #self.c.restore()
        self.draw_element('pagestr')

    def draw_cover(self):
        """Draw a coverpage."""
        # clip page print extents
        self.c.save()
        self.c.rectangle(self.printmargin, self.printmargin, 
                         self.printw, self.printh)
        self.c.clip()
        # draw page template
        if self.provisional:
            self.draw_provisional()

        # place cover image
        self.coverpage.draw(self.c)

        # if requested, overlay page marks
        if self.pagemarks:
            self.draw_pagemarks()

        # restore context
        self.c.restore()

    def draw_page(self, page_nr):
        """Draw the current page onto current context."""

        # clip page print extents
        self.c.save()
        self.c.rectangle(self.printmargin, self.printmargin, 
                         self.printw, self.printh)
        self.c.clip()

        # initialise status values
        self.curpage = page_nr + 1
        self.h = self.body_top
        self.strings['pagestr'] = 'Page ' + str(self.curpage)
        if self.get_pages() > 0:
            self.strings['pagestr'] += ' of ' + str(self.get_pages())

        # draw page template
        if self.provisional:
            self.draw_provisional()
        self.draw_template()

        # draw page content
        if self.get_pages() > page_nr:
            for s in self.pages[page_nr]:
                s.draw_pdf(self)	# call into section to draw
                self.h += self.line_height # inter-section gap

        # if requested, overlay page marks
        if self.pagemarks:
            self.draw_pagemarks()

        # restore context
        self.c.restore()

    def paragraph_height(self, text, width=None):
        """Determine height of a paragraph at the desired width."""
        ret = 0
        if width is None:
            width = self.body_width
        l = PangoCairo.create_layout(self.c)
        if self.fonts['body'] is not None:
            l.set_font_description(self.fonts['body'])
        l.set_width(int(Pango.SCALE * width + 1))
        l.set_wrap(Pango.WrapMode.WORD_CHAR)
        l.set_alignment(Pango.Alignment.LEFT)
        l.set_text(text, -1)
        (tw,th) = l.get_pixel_size()
        ret = th
        return ret
    
    def preformat_height(self, rows):
        """Determine height of a block of preformatted text."""
        ret = 0
        if len(rows) > 0:
            ostr = 'M' + 'L\n'*(len(rows)-1) + 'LM'
            l = PangoCairo.create_layout(self.c)
            if self.fonts['monospace'] is not None:
                l.set_font_description(self.fonts['monospace'])
            l.set_text(ostr, -1)
            (tw,th) = l.get_pixel_size()
            ret = th
        return ret

    def column_height(self, rows):
        """Determine height of column."""
        ret = 0
        rvec = []
        for r in rows:
            nval = 'M'
            rvec.append(nval)
        if len(rvec) > 0:
            l = PangoCairo.create_layout(self.c)
            if self.fonts['body'] is not None:
                l.set_font_description(self.fonts['body'])
            l.set_text('\n'.join(rvec), -1)
            (tw,th) = l.get_pixel_size()
            ret = th
        return ret

    def output_column(self, rows, col, align, oft):
        """Draw a single column."""
        ret = 0
        rvec = []
        oneval = False
        for r in rows:
            nval = ''
            if len(r) == 2:
                # special case... 
                if col == 2 and r[1]:
                    nval = str(r[1])	# is this req'd?
                    oneval = True
                elif col == 1 and r[0]:
                    nval = str(r[0])
                    oneval = True
            elif len(r) > col and r[col]:
                nval = str(r[col])
                oneval = True
            rvec.append(nval)
        if oneval:
            if align == 'l':
                (junk,ret) = self.text_left(oft, self.h, '\n'.join(rvec),
                                     self.fonts['body'])
            else:
                (junk,ret) = self.text_right(oft, self.h, '\n'.join(rvec),
                                     self.fonts['body'])
        return ret
            
    def newpage(self):
        """Called within paginate to add new page."""
        self.h = self.body_top
        curpage = []
        self.pages.append(curpage)
        return curpage

    def pagerem(self):
        """Within paginate, remaining vertical space on current page."""
        return self.body_bot - self.h

    def pagefrac(self):
        """Within paginate, fractional position on page."""
        return (self.h-self.body_top) / self.body_len

    def paginate(self):
        """Scan report content and paginate sections."""

        # initialise
        self.pages = []
        curpage = self.newpage()

        for r in self.sections:
            s = r
            while s is not None:
                if isinstance(s, pagebreak):
                    bpoint = s.get_threshold()
                    if bpoint is None:
                        bpoint = self.minbreak
                    if self.pagefrac() > bpoint:
                        curpage = self.newpage() # conditional break
                    s = None
                else:
                    (o, s) = s.truncate(self.pagerem(), self)
                    if isinstance(o, pagebreak):
                        curpage = self.newpage() # mandatory break
                    else:
                        curpage.append(o)
                        self.h += o.get_h(self)
                        if s is not None:	# section broken to new page
                            curpage = self.newpage()
                        else:
                            self.h += self.line_height # inter sec gap
        
    def draw_pagemarks(self):
        """Draw page layout markings on current page."""
        dash = [mm2pt(1)]
        self.c.save()	# start group
        self.c.set_dash(dash)
        self.c.set_line_width(0.5)
        self.c.set_source_rgb(0.0, 0.0, 1.0)

        # Lay lines
        self.c.move_to(0, 0)
        self.c.line_to(self.pagew, self.pageh)
        self.c.move_to(0, self.pageh)
        self.c.line_to(self.pagew, 0)

        # Page width circles
        self.c.move_to(0, self.midpagew)
        self.c.arc(self.midpagew, self.midpagew, self.midpagew, math.pi, 0.0)
        self.c.move_to(self.pagew, self.pageh-self.midpagew)
        self.c.arc(self.midpagew, self.pageh-self.midpagew, self.midpagew,
                     0.0, math.pi)
        self.c.stroke()

        # Body cropping from page geometry
        self.c.set_source_rgb(0.0, 1.0, 0.0)
        self.c.move_to(0, self.body_top)
        self.c.line_to(self.pagew, self.body_top)
        self.c.move_to(self.body_left,0)
        self.c.line_to(self.body_left,self.pageh)
        self.c.move_to(0, self.body_bot)
        self.c.line_to(self.pagew, self.body_bot)
        self.c.move_to(self.body_right,0)
        self.c.line_to(self.body_right,self.pageh)
        self.c.stroke()

        self.c.restore() # end group

    def get_baseline(self, h):
        """Return the baseline for a given height."""
        return h + 0.9 * self.line_height	# check baseline at other sz

    def laplines24(self, h, laps, start, finish, endh=None, reverse=False):
        ## LAZY
        self.c.save()
        sp = self.col_oft_cat - mm2pt(20.0)
        fac = mm2pt(40.0) / float(86450)
        top = h+0.15*self.line_height
        bot = h+0.85*self.line_height
        if reverse:
            self.c.set_source_rgba(0.5, 0.5, 0.5, 0.3)
        if endh is not None:
            bot = endh-0.15*self.line_height
        lp = None
        for l in laps:
            lt = None
            if lp is not None and not reverse:
                lt = l-lp
                if lt < tod.tod('2:30'):
                    self.c.set_source_rgba(0.0,0.0,0.0,1.0)
                elif lt < tod.tod('3:00'):
                    self.c.set_source_rgba(0.1,0.1,0.1,1.0)
                elif lt < tod.tod('3:30'):
                    self.c.set_source_rgba(0.3,0.3,0.3,1.0)
                elif lt < tod.tod('4:00'):
                    self.c.set_source_rgba(0.5,0.5,0.5,1.0)
                elif lt < tod.tod('4:30'):
                    self.c.set_source_rgba(0.6,0.6,0.6,1.0)
                elif lt < tod.tod('5:00'):
                    self.c.set_source_rgba(0.7,0.7,0.7,1.0)
                else:
                    self.c.set_source_rgba(0.8,0.8,0.8,1.0)
            lp = l
            el = l-start
            if int(el.as_seconds()) <= 86450:
            ##if l > start and l < finish:
                toft = sp + float(el.timeval)*fac
                self.drawline(toft, top, toft, bot)
        if reverse:
            toft = sp + float(86400)*fac
            self.drawline(toft, top, toft, bot)
        self.c.restore()

    def laplines(self, h, laps, start, finish, endh=None, reverse=False):
        ## LAZY
        sp = self.col_oft_cat - mm2pt(20.0)
        fac = mm2pt(40.0) / float((finish - start).timeval) 
        top = h+0.15*self.line_height
        bot = h+0.85*self.line_height
        if reverse:
            self.c.save()
            self.c.set_source_rgba(0.5, 0.5, 0.5, 0.3)
        if endh is not None:
            bot = endh-0.15*self.line_height
        for l in laps:
            if l > start and l < finish:
                toft = sp + float((l-start).timeval)*fac
                self.drawline(toft, top, toft, bot)
        if reverse:
            self.c.restore()
        
    def judges_row(self, h, rvec, zebra=None, strikethrough=False):
        """Output a standard section row, and return the row height."""
        if zebra:
            self.drawbox(self.body_left-mm2pt(1), h,
                         self.body_right+mm2pt(1), h+self.line_height, 0.07)
        omap = vecmap(rvec,9)
        strikeright = self.col_oft_rank
        if omap[0]:
            font = self.fonts['body']
            if not omap[7]:
                font = self.fonts['bodyoblique']
            self.text_left(self.col_oft_rank, h,
                            omap[0], font)
        if omap[1]:
            self.text_right(self.col_oft_no, h,
                            omap[1], self.fonts['body'])
            strikeright = self.col_oft_rank
        if omap[2]:
            maxnamew = (self.col_oft_cat - mm2pt(25.0)) - self.col_oft_name
            (tw,th) = self.fit_text(self.col_oft_name, h, omap[2],
                                    maxnamew, font = self.fonts['body'])
            strikeright = self.col_oft_name + tw
        if omap[3]:
            (tw,th) = self.text_left(self.col_oft_cat-mm2pt(25.0), h,
                            omap[3], self.fonts['body'])
            strikeright = self.col_oft_cat + tw
        if omap[4]:
            self.text_right(self.col_oft_time, h,
                            omap[4], self.fonts['body'])
            strikeright = self.col_oft_time
        if omap[5]:
            self.text_right(self.col_oft_xtra, h,
                            omap[5], self.fonts['body'])
            strikeright = self.col_oft_xtra
        if strikethrough:
            self.drawline(self.body_left+mm2pt(1),
                          h+(0.5*self.line_height),
                          strikeright,
                          h+(0.5*self.line_height))
        return self.line_height

    def gamut_cell(self, h, x, height, width, key, alpha=0.05, fonts={},
                                            data=None):
        """Draw a gamut cell and add data if available."""
        self.drawbox(x, h, x+width-mm2pt(0.5),h+height-mm2pt(0.5), alpha)
        if key:
            self.text_left(x+mm2pt(0.5), h-(0.07*height), key, fonts['key'])
        if data is not None:
            if data['name']:
                self.fit_text(x+0.4*width, h+(0.05*height), data['name'],
                              0.55*width, align=1.0, font=fonts['text'])
            if data['gcline']:
                self.text_right(x+width-mm2pt(1.0), h+(0.30*height),
                                data['gcline'], fonts['gcline'])
            if data['ltext']:
                self.text_left(x+mm2pt(0.5), h+(0.66*height),
                                data['ltext'], fonts['text'])
            if data['rtext']:
                self.text_right(x+width-mm2pt(1.0), h+(0.66*height),
                                data['rtext'], fonts['text'])
            if data['dnf']:
                self.drawline(x+mm2pt(0.5), h+height-mm2pt(1.0),
                              x+width-mm2pt(1.0), h+mm2pt(0.5), width=1.5)
        return height

    def standard_row(self, h, rvec, zebra=None, strikethrough=False):
        """Output a standard section row, and return the row height."""
        if zebra:
            self.drawbox(self.body_left-mm2pt(1), h,
                         self.body_right+mm2pt(1), h+self.line_height, 0.07)
        omap = vecmap(rvec,7)
        strikeright = self.col_oft_rank
        if omap[0]:
            self.text_left(self.col_oft_rank, h,
                            omap[0], self.fonts['body'])
        if omap[1]:
            self.text_right(self.col_oft_no, h,
                            omap[1], self.fonts['body'])
            strikeright = self.col_oft_rank
        if omap[2]:
            maxnamew = self.col_oft_cat - self.col_oft_name
            if not omap[3]:
                maxnamew = self.col_oft_time - self.col_oft_name - mm2pt(20)
            (tw,th) = self.fit_text(self.col_oft_name, h, omap[2],
                                    maxnamew, font = self.fonts['body'])
            strikeright = self.col_oft_name + tw
        if omap[3]:
            (tw,th) = self.text_left(self.col_oft_cat, h,
                            omap[3], self.fonts['body'])
            strikeright = self.col_oft_cat + tw
        if omap[4]:
            self.text_right(self.col_oft_time, h,
                            omap[4], self.fonts['body'])
            strikeright = self.col_oft_time
        if omap[5]:
            self.text_right(self.col_oft_xtra, h,
                            omap[5], self.fonts['body'])
            strikeright = self.col_oft_xtra
        if strikethrough:
            self.drawline(self.body_left+mm2pt(1),
                          h+(0.5*self.line_height),
                          strikeright,
                          h+(0.5*self.line_height))
        return self.line_height

    def rttstart_row(self, h, rvec, zebra=None, strikethrough=False):
        """Output a time trial start row, and return the row height."""
        if zebra:
            self.drawbox(self.body_left-mm2pt(1), h,
                         self.body_right+mm2pt(1), h+self.line_height, 0.07)
        omap = vecmap(rvec,7)
        strikeright = self.col_oft_name+mm2pt(16)
        if omap[0]:
            self.text_right(self.col_oft_name+mm2pt(1), h,
                            omap[0], self.fonts['body'])
        if omap[4]:
            self.text_left(self.col_oft_name+mm2pt(2), h,
                            omap[4], self.fonts['body'])
        if omap[1]:
            self.text_right(self.col_oft_name+mm2pt(16), h,
                            omap[1], self.fonts['body'])
        if omap[2]:
            maxnamew = self.col_oft_cat - self.col_oft_name # both oft by 20
            if not omap[3]:
                maxnamew = self.col_oft_xtra - self.col_oft_name
            (tw,th) = self.fit_text(self.col_oft_name+mm2pt(20), h,
                                    omap[2], maxnamew,
                                    font=self.fonts['body'])
            #(tw,th) = self.text_left(self.col_oft_name+mm2pt(20), h,
                            #omap[2], self.fonts[u'body'])
            strikeright = self.col_oft_name+mm2pt(20) + tw
        if omap[3]:
            (tw,th) = self.text_left(self.col_oft_cat+mm2pt(20), h,
                            omap[3], self.fonts['body'])
            strikeright = self.col_oft_cat+mm2pt(20) + tw
        if omap[5]:
            self.text_right(self.col_oft_xtra, h,
                            omap[5], self.fonts['body'])
            strikeright = self.body_right-mm2pt(1)
        if strikethrough:
            self.drawline(self.body_left+mm2pt(1),
                          h+(0.5*self.line_height),
                          strikeright,
                          h+(0.5*self.line_height))
        return self.line_height
        
    def ittt_lane(self, rvec, w, h, drawline = True):
        """Draw a single lane."""
        baseline = self.get_baseline(h)
        if rvec[0] is None:	# rider no None implies no rider
            self.text_left(w+mm2pt(8), h, '[No Rider]', self.fonts['body'])
        else:
            if rvec[0]:		# non-empty rider no implies full info
                self.text_right(w+mm2pt(7), h, rvec[0], self.fonts['body'])
                self.text_left(w+mm2pt(8), h, rvec[1], self.fonts['body'])
            else:		# otherwise draw placeholder lines
                self.drawline(w, baseline, w+mm2pt(7), baseline)
                self.drawline(w+mm2pt(8), baseline, w+mm2pt(58), baseline)
            if drawline:
                self.drawline(w+mm2pt(59), baseline, w+mm2pt(75), baseline)
            
    def ittt_heat(self, hvec, h, dual=False, showheat=True):
        """Output a single time trial heat."""
        if showheat:
            # allow for a heat holder but no text...
            if hvec[0] and hvec[0] != '-':
                self.text_left(self.body_left, h, 'Heat ' + str(hvec[0]),
                               self.fonts['subhead'])
            h += self.line_height
        rcnt = 1	# assume one row unless team members
        tcnt = 0
        if len(hvec) > 3:	# got a front straight
            self.ittt_lane([hvec[1], hvec[2]], self.body_left, h)
            if isinstance(hvec[3], list): # additional 'team' rows
                tcnt = len(hvec[3])
                tof = h + self.line_height
                for t in hvec[3]:
                    self.ittt_lane([t[0], t[1]], self.body_left,
                                    tof, drawline=False) 
                    tof += self.line_height
        if len(hvec) > 7: 	# got a back straight
            if hvec[5] is not None:
                self.text_cent(self.midpagew, h, 'v', self.fonts['subhead'])
            self.ittt_lane([hvec[5], hvec[6]], self.midpagew+mm2pt(5), h)
            if isinstance(hvec[7], list): # additional 'team' rows
                tcnt = max(tcnt, len(hvec[7]))
                tof = h + self.line_height
                for t in hvec[7]:
                    self.ittt_lane([t[0], t[1]], self.midpagew+mm2pt(5),
                                    tof, drawline=False)
                    tof += self.line_height
        elif dual:
            # No rider, but other heats are dual so add marker
            self.ittt_lane([None, None], self.midpagew+mm2pt(5), h)
        h += (rcnt+tcnt)*self.line_height

        return h

    def sprint_rider(self, rvec, w, h):
        baseline = self.get_baseline(h)
        # ignore rank in sprint round - defer to other markup
        doline = True
        if rvec[1]:	# rider no
            self.text_right(w+mm2pt(5.0), h, rvec[1], self.fonts['body'])
            doline = False
        if rvec[2]:	# rider name
            self.text_left(w+mm2pt(6.0), h, rvec[2], self.fonts['body'])
            doline = False
        if doline:
            self.drawline(w+mm2pt(1.0), baseline, w+mm2pt(50), baseline)
        # ignore cat/xtra in sprint rounds

    def sign_box(self, rvec, w, h, lineheight, zebra):
        baseline = h+lineheight+lineheight
        if zebra:
            self.drawbox(w, h,
                         w+self.twocol_width, baseline, 0.07)
        self.drawline(w, baseline, w+self.twocol_width, baseline)
        if len(rvec)>1 and rvec[1]:	# rider no
            self.text_right(w+mm2pt(7.0), h, rvec[1], self.fonts['body'])
        if len(rvec)>2 and rvec[2]:	# rider name
            self.fit_text(w+mm2pt(9.0), h, rvec[2],
                           self.twocol_width-mm2pt(9.0), 
                           font=self.fonts['body'])
            if rvec[0] == 'dns':
                mgn = mm2pt(1.5)
                self.drawline(w+mgn, h+mgn,
                               w+self.twocol_width-mgn, baseline-mgn)

    def rms_rider(self, rvec, w, h):
        baseline = self.get_baseline(h)
        if len(rvec)>0 and rvec[0] is not None:
            self.text_left(w, h, rvec[0], self.fonts['body'])
        else:
            self.drawline(w, baseline, w+mm2pt(4), baseline)
        doline = True
        if len(rvec)>1 and rvec[1]:     # rider no
            self.text_right(w+mm2pt(10.0), h, rvec[1], self.fonts['body'])
            doline = False
        if len(rvec)>2 and rvec[2]:     # rider name
            #self.text_left(w+mm2pt(11.0), h, rvec[2], self.fonts[u'body'])
            self.fit_text(w+mm2pt(11.0), h, rvec[2], mm2pt(50), 
                                    font=self.fonts['body'])
            doline = False
        if doline:
            self.drawline(w+mm2pt(8.0), baseline, w+mm2pt(60), baseline)
        if len(rvec)>3 and rvec[3]:     # cat/hcap/draw/etc
            self.text_left(w+mm2pt(62.0), h, rvec[3], self.fonts['bodyoblique'])

    def text_right(self, w, h, msg, font=None,
                         strikethrough=False, maxwidth=None):
        l = PangoCairo.create_layout(self.c)
        l.set_alignment(Pango.Alignment.RIGHT)
        if font is not None:
            l.set_font_description(font)
        l.set_text(msg, -1)
        (tw,th) = l.get_pixel_size()
        self.c.move_to(w-tw, h)
        PangoCairo.update_layout(self.c, l)
        PangoCairo.show_layout(self.c, l)
        return (tw,th)

    def drawbox(self, x1, y1, x2, y2, alpha=0.1):
        self.c.save()
        self.c.set_source_rgba(0.0, 0.0, 0.0, alpha)
        self.c.move_to(x1, y1)
        self.c.line_to(x2, y1)
        self.c.line_to(x2, y2)
        self.c.line_to(x1, y2)
        self.c.close_path()
        self.c.fill()
        self.c.restore()
       
    def drawline(self, x1, y1, x2, y2, width=0.5):
        self.c.save()
        self.c.set_line_width(width)
        self.c.move_to(x1, y1)
        self.c.line_to(x2, y2)
        self.c.stroke()
        self.c.restore()

    def fit_text(self, w, h, msg, maxwidth, align=0, font=None,
                       strikethrough=False):
        if msg is not None:
            self.c.save()
            l = PangoCairo.create_layout(self.c)
            l.set_alignment(Pango.Alignment.LEFT)	# superfluous?
            if font is not None:
                l.set_font_description(font)
            l.set_text(msg, -1)
            (tw,th) = l.get_pixel_size()
            oft = 0.0
            if align != 0 and tw < maxwidth:
                oft = align * (maxwidth - tw)   # else squish
            self.c.move_to(w+oft, h)  # move before applying conditional scale
            if tw > maxwidth:
                self.c.scale(float(maxwidth)/float(tw),1.0)
                tw = maxwidth
            PangoCairo.update_layout(self.c, l)
            PangoCairo.show_layout(self.c, l)
            if strikethrough:
                self.drawline(w, h+(0.85*th), w+tw, h+(0.15*th))
            self.c.restore()
            return (tw,th)

    def text_left(self, w, h, msg, font=None,
                        strikethrough=False, maxwidth=None):
        l = PangoCairo.create_layout(self.c)
        l.set_alignment(Pango.Alignment.LEFT)
        if font is not None:
            l.set_font_description(font)
        l.set_text(msg, -1)
        (tw,th) = l.get_pixel_size()
        self.c.move_to(w, h)
        PangoCairo.update_layout(self.c, l)
        PangoCairo.show_layout(self.c, l)
        if strikethrough:
            self.drawline(w, h+(th/2), w+tw, h+(th/2))
        return (tw,th)

    def text_para(self, w, h, text, font=None, width=None):
        if width is None:
            width = self.body_width
        l = PangoCairo.create_layout(self.c)
        if font is not None:
            l.set_font_description(font)
        l.set_width(int(Pango.SCALE * width + 1))
        l.set_wrap(Pango.WrapMode.WORD_CHAR)
        l.set_alignment(Pango.Alignment.LEFT)
        l.set_text(text, -1)
        (tw,th) = l.get_pixel_size()
        self.c.move_to(w, h)
        PangoCairo.update_layout(self.c, l)
        PangoCairo.show_layout(self.c, l)
        return (tw,th)

    def text_cent(self, w, h, msg, font=None, halign=Pango.Alignment.CENTER):
        l = PangoCairo.create_layout(self.c)
        l.set_alignment(halign)
        if font is not None:
            l.set_font_description(font)
        l.set_text(msg, -1)
        (tw,th) = l.get_pixel_size()
        self.c.move_to(w-(0.5 * tw), h)
        PangoCairo.update_layout(self.c, l)
        PangoCairo.show_layout(self.c, l)
        return (tw,th)

    def text_path(self, w, h, msg, font=None):
        l = PangoCairo.create_layout(self.c)
        if font is not None:
            l.set_font_description(font)
        l.set_text(msg, -1)
        (tw,th) = l.get_pixel_size()
        self.c.move_to(w-(0.5 * tw), h)
        PangoCairo.update_layout(self.c, l)
        PangoCairo.layout_path(self.c, l)
        self.c.fill()
        return (tw,th)

    def draw_provisional(self):
        self.c.save()
        self.c.set_source_rgb(1.0,1.0,1.0)
        self.text_cent(self.midpagew, self.body_top - mm2pt(5), 
                       'PROVISIONAL', self.fonts['body'])
        self.c.set_source_rgb(0.90, 0.90, 0.90)
        self.c.rectangle(self.body_left-20, self.body_top-20,
                         self.body_right - self.body_left + 40,
                         self.body_bot - self.body_top + 40)
        self.c.clip()
        self.c.translate(self.midpagew, self.midpageh)
        self.c.rotate(0.95532)
        self.text_path(0, -380,
          'PROVISIONAL\nPROVISIONAL\nPROVISIONAL\nPROVISIONAL\nPROVISIONAL',
                       self.fonts['provisional'])
        self.c.restore()

CSV_REPORT_SECTIONS = {
	'dualittt':	dual_ittt_startlist,
	'signon':	signon_list,
	'twocol':	twocol_startlist,
	'sprintround':	sprintround,
	'sprintfinal': sprintfinal,
	'rttstartlist':	rttstartlist,
	'list':	bullet_text,
	'bullet':	bullet_text,
	'pretext':	preformat_text,
        'eventindex':	event_index,
	'gamut':	gamut,
	'section':	section,

	'break':	pagebreak,
	'pagebreak':	pagebreak
}
