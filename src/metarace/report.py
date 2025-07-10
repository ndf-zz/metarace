# SPDX-License-Identifier: MIT
"""Report generation and printing support."""

import os
import gi

gi.require_version('Rsvg', '2.0')
from gi.repository import Rsvg

gi.require_version('Pango', '1.0')
from gi.repository import Pango

gi.require_version('PangoCairo', '1.0')
from gi.repository import PangoCairo

import cairo
import math
import xlsxwriter
import json
import time
import logging
import metarace
from metarace import tod
from metarace import strops
from metarace import htlib
from metarace import jsonconfig
from datetime import date, datetime, timezone

_log = logging.getLogger('report')
_log.setLevel(logging.DEBUG)

# JSON report API versioning
APIVERSION = '1.3.0'

# Spreadsheet style handles
XLSX_STYLE = {
    'left': None,
    'right': None,
    'title': None,
    'subtitle': None,
    'monospace': None,
}

# Meta cell icon classes
ICONMAP = {
    'datestr': 'bi-calendar-date',
    'docstr': 'bi-signpost-split',
    'diststr': 'bi-flag',
    'commstr': 'bi-person',
    'orgstr': 'bi-star',
    'download': 'bi-download',
    'default': 'bi-file-earmark'
}

# "download as" file types
FILETYPES = {'pdf': 'PDF', 'xlsx': 'Spreadsheet', 'json': 'JSON'}


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


# Transitional baseline position - to be replaced with font metrics
_CELL_BASELINE = 0.715

# defaults
PANGO_SCALE = float(Pango.SCALE)
PANGO_INVSCALE = 1.0 / float(Pango.SCALE)
FEPSILON = 0.0001  # float epsilon
BODYFONT = 'Nimbus Roman, Serif, 7.0'  # body text
BODYOBLIQUE = 'Nimbus Roman, Serif, Italic 7.0'  # body text italic
BODYBOLDFONT = 'Nimbus Roman, Serif, Bold 7.0'  # bold body text
BODYSMALL = 'Nimbus Roman, Serif, 6.0'  # small body text
MONOSPACEFONT = 'Nimbus Mono PS, Monospace, Bold 7.0'  # monospaced text
SECTIONFONT = 'Nimbus Sans, Sans-serif, Bold 7.0'  # section headings
SUBHEADFONT = 'Nimbus Roman, Serif, Italic 7.0'  # section subheadings
TITLEFONT = 'Nimbus Sans, Sans-serif, Bold 8.0'  # page title
SUBTITLEFONT = 'Nimbus Sans, Sans-serif, Bold 7.5'  # page subtitle
HOSTFONT = 'Nimbus Sans, Sans-serif, Italic 7.0'  # page title
ANNOTFONT = 'Nimbus Sans, Sans-serif, Italic 6.0'  # header and footer annotations
PROVFONT = 'Nimbus Sans Narrow, Sans-serif, Bold 90'  # provisonal underlay font
GAMUTSTDFONT = 'Nimbus Sans Narrow, Sans-serif, Bold'  # default gamut standard font
GAMUTOBFONT = 'Nimbus Sans Narrow, Sans-serif, Bold Oblique'  # default gamut oblique font
LINE_HEIGHT = mm2pt(5.0)  # body text line height
PAGE_OVERFLOW = mm2pt(3.0)  # tolerated section overflow
SECTION_HEIGHT = mm2pt(5.3)  # height of section title
TWOCOL_WIDTH = mm2pt(75.0)  # width of col on 2 col page
THREECOL_WIDTH = mm2pt(50.0)  # width of col on 3 col page
TABLESTYLE = 'table table-striped table-sm w-auto align-middle'  # html table style
BUTTONSTYLE = 'btn btn-primary btn-sm'  # html normal button link
WARNBUTTONSTYLE = 'btn btn-warning btn-sm'  # html provisional button link

UNITSMAP = {
    'mm': mm2pt,
    'cm': cm2pt,
    'in': in2pt,
    'pt': pt2pt,
}


def deg2rad(deg=1):
    """convert degrees to radians."""
    return math.pi * float(deg) / 180.0


def pi2rad(ang=1):
    """convert multiple of pi to radians."""
    return math.pi * float(ang)


def rad2rad(ang=1):
    """Dummy converter."""
    return ang


ANGUNITSMAP = {
    'dg': deg2rad,
    'pi': pi2rad,
    'rd': rad2rad,
}


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
    if anglestr:
        try:
            fval = float(val)
        except Exception as e:
            _log.warning('Invalid angle %r ignored: %s', anglestr, e)
    return ANGUNITSMAP[ukey](fval)


def str2align(alignstr=None):
    """Return an alignment value 0.0 - 1.0."""
    if alignstr is None:
        alignstr = ''
    ret = 0.5
    if alignstr:
        try:
            ret = float(alignstr)
            if ret < 0.0:
                ret = 0.0
            elif ret > 1.0:
                ret = 1.0
        except Exception as e:
            _log.warning('Invalid alignment %r ignored: %s', alignstr, e)
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
    if lenstr:
        try:
            fval = float(val)
        except Exception as e:
            _log.warning('Invalid length %r ignored: %s', lenstr, e)
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


def str2colour(colstr=None):
    """Return a valid colour from supplied string."""
    ret = [0.0, 0.0, 0.0]
    if colstr:
        cvec = colstr.split(',')
        if len(cvec) == 3:
            try:
                for c in range(0, 3):
                    ret[c] = float(cvec[c])
                    if ret[c] < 0.0:
                        ret[c] = 0.0
                    elif ret[c] > 1.0:
                        ret[c] = 1.0
            except Exception as e:
                _log.warning('Invalid colour %r ignored: %s', colstr, e)
    return ret


def mksectionid(curset, prefix=None):
    """Return a unique id for the section."""
    if prefix is None:
        prefix = ''
    else:
        prefix = prefix.lower().strip()
    if not prefix:
        prefix = 'sec'
        testid = prefix + strops.randstr()
    else:
        testid = prefix
    while testid in curset:
        testid = prefix + strops.randstr()
    return testid


def vecmap(vec=[], maxkey=10):
    """Return a full map for the supplied vector."""
    ret = {}
    for i in range(0, maxkey):
        ret[i] = None
    if vec is not None:
        for i in range(0, len(vec)):
            if vec[i]:
                if isinstance(vec[i], str):
                    ret[i] = vec[i].strip(' \t')  # just strip plain spaces
                else:
                    ret[i] = vec[i]
    return ret


def vecmapstr(vec=[], maxkey=10):
    """Return a full map for the supplied vector, converted to strings."""
    ret = {}
    for i in range(0, maxkey):
        ret[i] = ''
    for i in range(0, len(vec)):
        if vec[i]:
            ret[i] = str(vec[i]).strip()
    return ret


def vec2htmllinkrow(vec=[], xtn='', rep=None):
    # evno -> column one
    # N/A
    # descr -> column two
    # text
    # link
    # text
    # link
    rowmap = vecmapstr(vec, 7)
    cols = []
    cols.append(htlib.td(rowmap[0]))
    if rowmap[6]:  # Startlist/Result links
        cols.append(htlib.td(rowmap[2]))  # DESCR
        bstyle = rep.buttonstyle
        stxt = ''
        if rowmap[4]:  # 'startlist' is present
            ltxt = 'Startlist'
            flnk = rowmap[4] + xtn
            if rowmap[3]:
                ltxt = rowmap[3]
                flnk = rowmap[4]
            stxt = htlib.a(ltxt, {'href': flnk, 'class': bstyle})
        rtxt = ''
        if rowmap[6]:  # result is present
            ltxt = 'Result'
            flnk = rowmap[6] + xtn
            if rowmap[5]:
                ltxt = rowmap[5]
                flnk = rowmap[6]
            rtxt = htlib.a(ltxt, {'href': flnk, 'class': bstyle})
        cols.append(htlib.td(stxt))
        cols.append(htlib.td(rtxt))
    else:  # Old-style trackmeet event index
        if rowmap[4]:
            url = rowmap[4] + xtn
            if rowmap[5]:  # in-page target
                url += '#' + rowmap[5]
            cols.append(htlib.td(htlib.a(rowmap[2], {'href': url})))
        else:
            cols.append(htlib.td(rowmap[2]))
        cols.append(htlib.td(rowmap[3]))
        # cols.append(htlib.td(rowmap[5]))
    return htlib.tr(cols)


def vec2htmlrow(vec=[], maxcol=7):
    rowmap = vecmapstr(vec, maxcol)
    cols = []
    cols.append(htlib.td(rowmap[0]))  # Rank (left)
    cols.append(htlib.td(rowmap[1], {'class': 'text-end'}))  # No (right)
    cols.append(htlib.td(rowmap[2]))  # Name (left)
    cols.append(htlib.td(rowmap[3]))  # Cat/Code (left)
    for c in range(4, maxcol):
        cols.append(htlib.td(rowmap[c], {'class': 'text-end'}))  # right
    return htlib.tr(cols)


def vec2htmlhead(vec=[], maxcol=7):
    rowmap = vecmapstr(vec, maxcol)
    cols = []
    cols.append(htlib.th(rowmap[0]))  # Rank (left)
    cols.append(htlib.th(rowmap[1], {'class': 'text-end'}))  # No (right)
    cols.append(htlib.th(rowmap[2]))  # Name (left)
    cols.append(htlib.th(rowmap[3]))  # Cat/Code (left)
    for c in range(4, maxcol):
        cols.append(htlib.th(rowmap[c], {'class': 'text-end'}))  # right
    return htlib.tr(cols)


class _publicEncoder(json.JSONEncoder):
    """Encode tod, agg, datetime and dates"""

    def default(self, obj):
        if isinstance(obj, tod.tod):
            b = (obj.timeval * 0).as_tuple()
            places = min(-(b.exponent), 5)
            return obj.isostr(places)  # retain truncation of original value
        elif type(obj) is datetime:
            ts = 'seconds'
            if obj.microsecond:
                ts = 'milliseconds'
            return obj.isoformat(timespec=ts)
        elif isinstance(obj, date):
            return obj.isoformat()
        return json.JSONEncoder.default(self, obj)


# Section Types
class dual_ittt_startlist:
    """Two-up time trial for individual riders (eg track pursuit)."""

    def __init__(self, secid=''):
        self.sectionid = secid
        self.heading = None
        self.status = None
        self.subheading = None
        self.footer = None
        self.colheader = None  # ignored for dual ittt
        self.showheats = False  # show heat labels?
        self.units = None
        self.lines = []
        self.fslbl = 'Front Straight'
        self.bslbl = 'Back Straight'
        self.lcount = 0
        self.nobreak = False
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
            if self.showheats:  # if heats are shown, double line height
                self.h *= 2
            for r in self.lines:  # account for any team members
                tcnt = 0
                if len(r) > 3 and isinstance(r[3], (tuple, list)):
                    tcnt = len(r[3])
                if len(r) > 7 and isinstance(r[7], (tuple, list)):
                    tcnt = max(tcnt, len(r[7]))
                if tcnt > 0:
                    self.h += tcnt * report.line_height
            if self.heading:
                self.h += report.section_height
            if self.subheading:
                self.h += report.section_height
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

        # Special case: Don't break if possible
        if self.nobreak and report.pagefrac() > FEPSILON:
            # move entire section onto next page
            return (pagebreak(0.01), self)

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
        if len(self.lines) <= 4:  # special case, keep four or less together
            chk.lines = self.lines[0:]
        else:  # BUT, don't break before third rider
            chk.lines = self.lines[0:2]
        if chk.get_h(report) > remainder:
            # move entire section onto next page
            return (pagebreak(0.01), self)

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
            while count < seclines and count < 3:  # don't break until 3rd
                ret.lines.append(self.lines[count])
                count += 1
        while count < seclines:
            if ret.get_h(report) > remainder:
                # pop last line onto rem and break
                rem.lines.append(ret.lines.pop(-1))
                break
            elif seclines - count <= 2:  # push min 2 names over to next page
                break
            ret.lines.append(self.lines[count])
            count += 1
        while count < seclines:
            rem.lines.append(self.lines[count])
            count += 1
        return (ret, rem)

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
            report.h += report.section_height
        dolanes = False
        dual = False
        if self.fslbl:
            report.text_cent(report.midpagew - mm2pt(40), report.h, self.fslbl,
                             report.fonts['subhead'])
            dolanes = True
        if self.bslbl:
            report.text_left(report.midpagew + mm2pt(40), report.h, self.bslbl,
                             report.fonts['subhead'])
            dolanes = True
            dual = True  # heading flags presense of back straight
        if dolanes:
            report.h += report.line_height  # account for lane label h
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

    def draw_xlsx(self, report, worksheet):
        """Output program element to excel worksheet."""
        row = report.h
        if self.heading:
            worksheet.write(row, 2, self.heading.strip(), XLSX_STYLE['title'])
            row += 1
        if self.subheading:
            worksheet.write(row, 2,
                            self.subheading.replace('\t', '  ').strip(),
                            XLSX_STYLE['subtitle'])
            row += 2
        else:
            row += 1  # min one clear row between
        dual = False
        if self.bslbl:
            dual = True
        if len(self.lines) > 0:
            rows = []
            for r in self.lines:
                nv = [None, None, None]
                if self.showheats and r[0] and r[0] != '-':
                    nv[0] = 'Heat ' + str(r[0])
                if len(r) > 3:  # front straight
                    nv[1] = r[1]
                    nv[2] = r[2]
                rows.append(nv)  # allow empty
                if len(r) > 3 and isinstance(r[3], (tuple, list)):
                    for tm in r[3]:
                        tv = [None, tm[0], tm[1]]
                        rows.append(tv)
                if len(r) > 7:  # back straight
                    nv = [None, r[5], r[6]]
                    rows.append(nv)
                elif dual:
                    rows.append([None, None, '[No Rider]'])
                if len(r) > 7 and isinstance(r[7], (tuple, list)):
                    for tm in r[7]:
                        tv = [None, tm[0], tm[1]]
                        rows.append(tv)

            for rw in rows:
                l = vecmapstr(rw)
                worksheet.write(row, 0, l[0], XLSX_STYLE['left'])
                worksheet.write(row, 1, l[1], XLSX_STYLE['right'])
                worksheet.write(row, 2, l[2], XLSX_STYLE['left'])
                worksheet.write(row, 3, l[3], XLSX_STYLE['left'])
                worksheet.write(row, 4, l[4], XLSX_STYLE['right'])
                worksheet.write(row, 5, l[5], XLSX_STYLE['right'])
                worksheet.write(row, 6, l[6], XLSX_STYLE['left'])
                row += 1
            row += 1
        if self.footer:
            worksheet.write(row, 2, self.footer.strip(),
                            XLSX_STYLE['subtitle'])
            row += 2
        report.h = row
        return None

    def draw_text(self, report, f, xtn):
        """Output program element in html."""
        if self.heading:
            f.write(htlib.h3(self.heading.strip(), {'id': self.sectionid}))
        if self.subheading:
            f.write(htlib.p(self.subheading.strip(), {'class': 'lead'}))
        dual = False
        if self.bslbl:
            dual = True
        if len(self.lines) > 0:
            rows = []
            for r in self.lines:
                nv = [None, None, None]
                if self.showheats and r[0] and r[0] != '-':
                    nv[0] = 'Heat ' + str(r[0]) + ':'
                if len(r) > 3:  # front straight
                    nv[1] = r[1]
                    nv[2] = r[2]
                rows.append(nv)
                if len(r) > 3 and isinstance(r[3], (tuple, list)):
                    for tm in r[3]:
                        tv = [None, tm[0], tm[1]]
                        rows.append(tv)
                if len(r) > 7:  # back straight
                    nv = [None, r[5], r[6]]
                    rows.append(nv)
                elif dual:
                    rows.append([None, None, '[No Rider]'])
                if len(r) > 7 and isinstance(r[7], (tuple, list)):
                    for tm in r[7]:
                        tv = [None, tm[0], tm[1]]
                        rows.append(tv)
            trows = []
            for l in rows:
                trows.append(vec2htmlrow(l))
            f.write(
                htlib.table(htlib.tbody(trows), {'class': report.tablestyle}))
            f.write('\n')

        if self.footer:
            f.write(htlib.p(self.footer.strip()))
        return False


class signon_list:

    def __init__(self, secid=''):
        self.sectionid = secid
        self.status = None
        self.heading = None
        self.subheading = None
        self.colheader = None  # ignored for all signon
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
                self.h += report.section_height
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
        if len(self.lines) <= 8:  # special case, keep first <=8 together
            chk.lines = self.lines[0:]
        else:
            chk.lines = self.lines[0:4]  # but don't break until 4 names
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
            while count < seclines and count < 4:  # don't break until 4th
                ret.lines.append(self.lines[count])
                count += 1
        while count < seclines:
            if ret.get_h(report) > remainder:
                # pop last line onto rem and break
                rem.lines.append(ret.lines.pop(-1))
                break
            elif seclines - count <= 3:  # push min 4 names over to next page
                break
            ret.lines.append(self.lines[count])
            count += 1
        while count < seclines:
            rem.lines.append(self.lines[count])
            count += 1
        return (ret, rem)

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
            report.h += report.section_height

        colof = report.body_left
        hof = report.h
        collen = int(math.ceil(0.5 * len(self.lines)))
        colcnt = 0
        if len(self.lines) > 0:
            for i in self.lines[0:collen]:
                if len(i) > 2:
                    report.sign_box(i, colof, hof, self.lineheight, colcnt % 2)
                hof += self.lineheight + self.lineheight
                colcnt += 1
            hof = report.h
            colof = report.body_right - report.twocol_width
            #colof = report.midpagew+mm2pt(2.0)
            colcnt = 0
            for i in self.lines[collen:]:
                if len(i) > 2:
                    report.sign_box(i, colof, hof, self.lineheight,
                                    (colcnt + 1) % 2)
                hof += self.lineheight + self.lineheight
                colcnt += 1
        report.h += 2.0 * collen * self.lineheight
        if self.footer:
            report.text_cent(report.midpagew, report.h, self.footer,
                             report.fonts['subhead'])
            report.h += report.line_height

    def draw_xlsx(self, report, worksheet):
        """Output program element to excel worksheet."""
        row = report.h
        if self.heading:
            worksheet.write(row, 2, self.heading.strip(), XLSX_STYLE['title'])
            row += 1
        if self.subheading:
            worksheet.write(row, 2,
                            self.subheading.replace('\t', '  ').strip(),
                            XLSX_STYLE['subtitle'])
            row += 2
        else:
            row += 1  # min one clear row between

        if len(self.lines) > 0:
            rows = []
            for r in self.lines:
                nv = r[0:6]
                if len(nv) == 2:
                    nv = [nv[0], None, nv[1]]
                rows.append(vecmapstr(nv, 7))
            for l in rows:
                worksheet.write(row, 0, l[0], XLSX_STYLE['left'])
                worksheet.write(row, 1, l[1], XLSX_STYLE['right'])
                worksheet.write(row, 2, l[2], XLSX_STYLE['left'])
                worksheet.write(row, 3, l[3], XLSX_STYLE['left'])
                worksheet.write(row, 4, l[4], XLSX_STYLE['right'])
                worksheet.write(row, 5, l[5], XLSX_STYLE['right'])
                worksheet.write(row, 6, l[6], XLSX_STYLE['left'])
                row += 1
            row += 1
        if self.footer:
            worksheet.write(row, 2, self.footer.strip(),
                            XLSX_STYLE['subtitle'])
            row += 2
        report.h = row
        return None

    def draw_text(self, report, f, xtn):
        """Write out a section in html."""
        if self.heading:
            f.write(htlib.h3(self.heading.strip(), {'id': self.sectionid}))
        if self.subheading:
            f.write(htlib.p(self.subheading.strip(), {'class': 'lead'}))
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
            f.write(
                htlib.table(htlib.tbody(trows), {'class': report.tablestyle}))
            f.write('\n')
        if self.footer:
            f.write(htlib.p(self.footer.strip()))
        return False


class twocol_startlist:

    def __init__(self, secid=''):
        self.sectionid = secid
        self.heading = None
        self.status = None
        self.subheading = None
        self.footer = None
        self.prizes = None
        self.timestr = None
        self.lines = []
        self.lcount = 0
        self.nobreak = False
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
        ret['prizes'] = self.prizes
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
                collen += 1  # force an even number of rows in first column.
            self.h = report.line_height * collen
            if self.heading:
                self.h += report.section_height
                self.preh += report.section_height
            if self.subheading:
                self.h += report.section_height
                self.preh += report.section_height
            if self.timestr:
                self.h += report.line_height
                self.preh += report.line_height
            if self.prizes:
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
            # Special case: Don't break if possible
            if self.nobreak and report.pagefrac() > FEPSILON:
                # move entire section onto next page
                return (pagebreak(0.01), self)

            if report.pagefrac() < FEPSILON:  # avoid error
                # there's a whole page's worth of space here, but a
                # break is required
                bodyh = remainder - self.preh  # preh comes from get_h
                maxlines = 2 * int(bodyh / report.line_height)  # floor
                # ret: content on current page
                # rem: content on subsequent pages
                ret = twocol_startlist()
                rem = twocol_startlist()
                ret.heading = self.heading
                ret.subheading = self.subheading
                ret.prizes = self.prizes
                ret.footer = self.footer
                if ret.footer:
                    ret.footer += ' Continued over\u2026'
                ret.timestr = self.timestr
                ret.lines = self.lines[0:maxlines]
                rem.heading = self.heading
                rem.subheading = self.subheading
                rem.footer = self.footer
                rem.prizes = self.prizes
                rem.timestr = self.timestr
                if rem.heading:
                    if rem.heading.rfind('(continued)') < 0:
                        rem.heading += ' (continued)'
                rem.lines = self.lines[maxlines:]
                return (ret, rem)
            else:
                # we are somewhere on the page - insert break and try again
                return (pagebreak(0.01), self)

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
            report.h += report.section_height

        #colof = report.body_left-mm2pt(10.0)
        colof = report.body_left
        hof = report.h
        collen = int(math.ceil(0.5 * len(self.lines)))
        if self.even and collen % 2:
            collen += 1  # force an even number of rows in first column.
        if len(self.lines) > 0:
            for i in self.lines[0:collen]:
                if len(i) > 2:
                    report.rms_rider(i, colof, hof)
                hof += report.line_height
            hof = report.h
            #colof = report.midpagew-mm2pt(5.0)
            colof = report.midpagew + mm2pt(2.0)
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
        if self.prizes:
            report.text_cent(report.midpagew, report.h, self.prizes,
                             report.fonts['subhead'])
            report.h += report.line_height
        if self.footer:
            report.text_cent(report.midpagew, report.h, self.footer,
                             report.fonts['subhead'])
            report.h += report.line_height
        report.c.restore()

    def draw_xlsx(self, report, worksheet):
        """Output program element to excel worksheet."""
        row = report.h
        if self.heading:
            worksheet.write(row, 2, self.heading.strip(), XLSX_STYLE['title'])
            row += 1
        if self.subheading:
            worksheet.write(row, 2,
                            self.subheading.replace('\t', '  ').strip(),
                            XLSX_STYLE['subtitle'])
            row += 2
        else:
            row += 1  # min one clear row between

        if len(self.lines) > 0:
            rows = []
            for r in self.lines:
                nv = r[0:6]
                if len(nv) == 2:
                    nv = [nv[0], None, nv[1]]
                rows.append(vecmapstr(nv, 7))
            for l in rows:
                worksheet.write(row, 0, l[0], XLSX_STYLE['left'])
                worksheet.write(row, 1, l[1], XLSX_STYLE['right'])
                worksheet.write(row, 2, l[2], XLSX_STYLE['left'])
                worksheet.write(row, 3, l[3], XLSX_STYLE['left'])
                worksheet.write(row, 4, l[4], XLSX_STYLE['right'])
                worksheet.write(row, 5, l[5], XLSX_STYLE['right'])
                worksheet.write(row, 6, l[6], XLSX_STYLE['left'])
                row += 1
            row += 1
        if self.prizes:
            worksheet.write(row, 2, self.prizes.strip(),
                            XLSX_STYLE['subtitle'])
            row += 1
        if self.footer:
            worksheet.write(row, 2, self.footer.strip(),
                            XLSX_STYLE['subtitle'])
            row += 2
        report.h = row
        return None

    def draw_text(self, report, f, xtn):
        """Write out a section in html."""
        if self.heading:
            f.write(htlib.h3(self.heading.strip(), {'id': self.sectionid}))
        if self.subheading:
            f.write(htlib.p(self.subheading.strip(), {'class': 'lead'}))
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
            f.write(
                htlib.table(htlib.tbody(trows), {'class': report.tablestyle}))
            f.write('\n')
        if self.prizes:
            f.write(htlib.p(self.prizes.strip(), {'class': 'text-italic'}))
        if self.footer:
            f.write(htlib.p(self.footer.strip()))
        return False


class sprintround:

    def __init__(self, secid=''):
        self.sectionid = secid
        self.heading = None
        self.status = None
        self.subheading = None
        self.colheader = None
        self.units = None
        self.footer = None
        self.lines = []  # maps to 'heats', include riders?
        self.lcount = 0
        self.nobreak = False
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
            self.h = report.line_height * len(self.lines)  # one per line?
            if self.heading:
                self.h += report.section_height
            if self.subheading:
                self.h += report.section_height
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
                raise RuntimeWarning(
                    'Section ' + repr(self.heading) +
                    ' will not fit on a page and will not break.')
            # move entire section onto next page
            return (pagebreak(0.01), self)

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
            report.h += report.section_height
        hof = report.h
        if len(self.lines) > 0:
            for i in self.lines:
                heat = ''
                if i[0]:
                    heat = i[0]
                if heat:
                    report.text_left(report.body_left, hof, heat,
                                     report.fonts['subhead'])
                report.sprint_rider(i[1], report.body_left + mm2pt(14), hof)
                report.sprint_rider(i[2], report.midpagew + mm2pt(4), hof)
                vstr = 'v'
                if i[1][0] and i[2][0]:  # assume result in order...
                    vstr = 'def'
                if i[2][0] == ' ':  # hack for bye
                    vstr = None
                if vstr:
                    report.text_cent(report.midpagew, hof, vstr,
                                     report.fonts['subhead'])
                time = ''
                if len(i) > 3 and i[3]:
                    time = i[3]  # probably already have a result
                if time:
                    report.text_right(report.body_right, hof, time,
                                      report.fonts['body'])
                else:
                    baseline = report.get_baseline(hof)
                    report.drawline(report.body_right - mm2pt(10), baseline,
                                    report.body_right, baseline)
                hof += report.line_height
        report.h = hof
        if self.footer:
            report.text_cent(report.midpagew, report.h, self.footer,
                             report.fonts['subhead'])
            report.h += report.line_height
        report.c.restore()

    def draw_xlsx(self, report, worksheet):
        """Output program element to excel worksheet."""
        row = report.h
        if self.heading:
            worksheet.write(row, 2, self.heading.strip(), XLSX_STYLE['title'])
            row += 1
        if self.subheading:
            worksheet.write(row, 2,
                            self.subheading.replace('\t', '  ').strip(),
                            XLSX_STYLE['subtitle'])
            row += 2
        else:
            row += 1  # min one clear row between
        if len(self.lines) > 0:
            rows = []
            for c in self.lines:  # each row is a pair/contest
                # 'a' rider
                rows.append([None, None, c[0], None, None])  # contest id)
                av = [None, None, None, None, None]
                av[0] = c[1][0]
                av[1] = c[1][1]
                av[2] = c[1][2]
                av[3] = c[1][3]
                if len(c) > 3 and c[3]:
                    av[4] = c[3]  # place 200m time in info col
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
                worksheet.write(row, 0, l[0], XLSX_STYLE['left'])
                worksheet.write(row, 1, l[1], XLSX_STYLE['right'])
                worksheet.write(row, 2, l[2], XLSX_STYLE['left'])
                worksheet.write(row, 3, l[3], XLSX_STYLE['left'])
                worksheet.write(row, 4, l[4], XLSX_STYLE['right'])
                worksheet.write(row, 5, l[5], XLSX_STYLE['right'])
                worksheet.write(row, 6, l[6], XLSX_STYLE['left'])
                row += 1
            row += 1
        if self.footer:
            worksheet.write(row, 2, self.footer.strip(),
                            XLSX_STYLE['subtitle'])
            row += 2
        report.h = row
        return None

    def draw_text(self, report, f, xtn):
        """Output program element in html."""
        if self.heading:
            f.write(htlib.h3(self.heading.strip(), {'id': self.sectionid}))
        if self.subheading:
            f.write(htlib.p(self.subheading.strip(), {'class': 'lead'}))
        if len(self.lines) > 0:
            rows = []
            for c in self.lines:  # each row is a pair/contest
                # 'a' rider
                rows.append([None, None, c[0], None, None])  # contest id)
                av = [None, None, None, None, None]
                av[0] = c[1][0]
                av[1] = c[1][1]
                av[2] = c[1][2]
                av[3] = c[1][3]
                if len(c) > 3 and c[3]:
                    av[4] = c[3]  # place 200m time in info col
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
            f.write(
                htlib.table(htlib.tbody(trows), {'class': report.tablestyle}))
            f.write('\n')
        if self.footer:
            f.write(htlib.p(self.footer.strip()))
        return ''


class sprintfinal:

    def __init__(self, secid=''):
        self.sectionid = secid
        self.status = None
        self.heading = None
        self.subheading = None
        self.colheader = None
        self.units = None
        self.footer = None
        self.lines = []  # maps to 'contests'
        self.lcount = 0
        self.nobreak = False
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
                self.h += report.section_height
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
                raise RuntimeWarning(
                    'Section ' + repr(self.heading) +
                    ' will not fit on a page and will not break.')
            # move entire section onto next page
            return (pagebreak(0.01), self)

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
            report.h += report.section_height
        heatlbls = False
        hof = report.h
        if len(self.lines) > 0:
            for i in self.lines:
                hw = mm2pt(20)
                hl = report.midpagew + hw
                h1t = hl + 0.5 * hw
                h2t = h1t + hw
                h12 = hl + hw
                h3t = h2t + hw
                h23 = h12 + hw
                hr = hl + 3.0 * hw

                # place heat headings
                if not heatlbls:
                    report.text_cent(h1t, hof, 'Heat 1',
                                     report.fonts['subhead'])
                    report.text_cent(h2t, hof, 'Heat 2',
                                     report.fonts['subhead'])
                    report.text_cent(h3t, hof, 'Heat 3',
                                     report.fonts['subhead'])
                    hof += report.line_height
                    heatlbls = True
                else:
                    hof += 0.3 * report.line_height

                heat = ''
                if i[0]:
                    heat = i[0]
                if heat:
                    report.text_left(report.body_left, hof, heat,
                                     report.fonts['subhead'])

                ht = hof
                bl = report.get_baseline(hof)
                hb = report.get_baseline(hof + report.line_height)
                # draw heat lines
                if 'bye' not in heat:
                    report.drawline(hl, bl, hr, bl)
                    report.drawline(h12, ht + 0.1 * report.line_height, h12,
                                    hb - 0.1 * report.line_height)
                    report.drawline(h23, ht + 0.1 * report.line_height, h23,
                                    hb - 0.1 * report.line_height)

                # draw all the "a" rider info
                report.sprint_rider(i[1], report.body_left + hw, hof)
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
                report.sprint_rider(i[2], report.body_left + hw, hof)
                if i[2][4]:
                    report.text_cent(h1t, hof, i[2][4], report.fonts['body'])
                if i[2][5]:
                    report.text_cent(h2t, hof, i[2][5], report.fonts['body'])
                if i[2][6]:
                    report.text_cent(h3t, hof, i[2][6], report.fonts['body'])
                #if len(i[2]) > 7 and i[2][7]:
                #report.text_left(hl, hof, i[2][7], report.fonts[u'body'])
                hof += report.line_height

                # cross-out heat three if not required
                if i[2][4] and i[2][5] or i[1][4] and i[1][5]:
                    report.drawline(h23 + 0.4 * report.line_height,
                                    hb - 0.2 * report.line_height,
                                    hr - 0.4 * report.line_height,
                                    ht + 0.2 * report.line_height)

        report.h = hof
        if self.footer:
            report.text_cent(report.midpagew, report.h, self.footer,
                             report.fonts['subhead'])
            report.h += report.line_height
        report.c.restore()

    def draw_xlsx(self, report, worksheet):
        """Output program element to excel worksheet."""
        row = report.h
        if self.heading:
            worksheet.write(row, 2, self.heading.strip(), XLSX_STYLE['title'])
            row += 1
        if self.subheading:
            worksheet.write(row, 2,
                            self.subheading.replace('\t', '  ').strip(),
                            XLSX_STYLE['subtitle'])
            row += 2
        else:
            row += 1  # min one clear row between
        if len(self.lines) > 0:
            rows = []
            rows.append([None, None, None, 'Heat 1', 'Heat 2', 'Heat 3'])
            for c in self.lines:  # each row is a pair/contest
                # 'a' rider
                av = [c[1][j] for j in [0, 1, 2, 4, 5, 6]]  # skip info col
                av[0] = c[0]
                rows.append(av)
                # 'b' rider
                bv = [c[2][j] for j in [0, 1, 2, 4, 5, 6]]
                bv[0] = None
                rows.append(bv)
                rows.append([])
            for rw in rows:
                l = vecmapstr(rw)
                worksheet.write(row, 0, l[0], XLSX_STYLE['left'])  # contest
                worksheet.write(row, 1, l[1], XLSX_STYLE['right'])  # no
                worksheet.write(row, 2, l[2], XLSX_STYLE['left'])  # name
                worksheet.write(row, 3, l[3], XLSX_STYLE['right'])  # heat 1
                worksheet.write(row, 4, l[4], XLSX_STYLE['right'])  # heat 2
                worksheet.write(row, 5, l[5], XLSX_STYLE['right'])  # heat 3
                #worksheet.write(row, 6, l[6], XLSX_STYLE['left'])	# comment?
                row += 1
            row += 1
        if self.footer:
            worksheet.write(row, 2, self.footer.strip(),
                            XLSX_STYLE['subtitle'])
            row += 2
        report.h = row
        return None

    def draw_text(self, report, f, xtn):
        """Output program element in html."""
        if self.heading:
            f.write(htlib.h3(self.heading.strip(), {'id': self.sectionid}))
        if self.subheading:
            f.write(htlib.p(self.subheading.strip(), {'class': 'lead'}))
        if len(self.lines) > 0:
            rows = []
            rows.append([None, None, None, 'Heat 1', 'Heat 2', 'Heat 3'])
            for c in self.lines:  # each row is a pair/contest
                # 'a' rider
                #rows.append([None,None,u'Heat 1',u'Heat 2',u'Heat 3'])
                av = [c[1][j] for j in [0, 1, 2, 4, 5, 6]]  # skip info col
                av[0] = c[0]
                rows.append(av)
                # 'b' rider
                bv = [c[2][j] for j in [0, 1, 2, 4, 5, 6]]
                bv[0] = None
                rows.append(bv)
                rows.append([])
            trows = []
            for l in rows:
                trows.append(vec2htmlrow(l))
            f.write(
                htlib.table(htlib.tbody(trows), {'class': report.tablestyle}))
            f.write('\n')
        if self.footer:
            f.write(htlib.p(self.footer.strip()))
        return ''


class rttstartlist:
    """Time trial start list."""

    def __init__(self, secid=''):
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
            if self.colheader:  # colheader is written out with body
                self.h += report.line_height
            if self.heading:
                self.h += report.section_height
            if self.subheading:
                self.h += report.section_height
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
        if len(self.lines) <= 4:  # special case, keep four or less together
            chk.lines = self.lines[0:]
        else:  # BUT, don't break before third rider
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
            while count < seclines and count < 3:  # don't break until 3rd
                ret.lines.append(self.lines[count])
                count += 1
        while count < seclines:
            if ret.get_h(report) > remainder:
                # pop last line onto rem and break
                rem.lines.append(ret.lines.pop(-1))
                break
            elif seclines - count <= 2:  # push min 2 names over to next page
                break
            ret.lines.append(self.lines[count])
            count += 1
        while count < seclines:
            rem.lines.append(self.lines[count])
            count += 1
        return (ret, rem)

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
            report.h += report.section_height
        cnt = 1
        if len(self.lines) > 0:
            if self.colheader:
                report.h += report.rttstart_row(report.h, self.colheader)
            for r in self.lines:
                if len(r) > 5:
                    if r[5] is not None and r[5].lower() == 'pilot':
                        r[5] = 'Pilot'
                    elif not (r[0] or r[1] or r[2] or r[3]):
                        cnt = 0  # empty row?
                    else:
                        cnt += 1
                else:
                    cnt = 0  # blank all 'empty' lines
                report.h += report.rttstart_row(report.h, r, cnt % 2)
        if self.footer:
            report.text_cent(report.midpagew, report.h, self.footer,
                             report.fonts['subhead'])
            report.h += report.line_height
        report.c.restore()

    def draw_xlsx(self, report, worksheet):
        """Output program element to excel worksheet."""
        row = report.h
        if self.heading:
            worksheet.write(row, 2, self.heading.strip(), XLSX_STYLE['title'])
            row += 1
        if self.subheading:
            worksheet.write(row, 2, self.subheading.strip(),
                            XLSX_STYLE['subtitle'])
            row += 2
        else:
            row += 1
        if len(self.lines) > 0:
            rows = []
            if self.colheader:
                rows.append(vecmapstr(self.colheader, 7))
            for r in self.lines:
                nv = r[0:6]
                if len(nv) == 2:
                    nv = [nv[0], None, nv[1]]
                rows.append(vecmapstr(nv, 7))
            for l in rows:
                worksheet.write(row, 0, l[0], XLSX_STYLE['left'])
                worksheet.write(row, 1, l[1], XLSX_STYLE['right'])
                worksheet.write(row, 2, l[2], XLSX_STYLE['left'])
                worksheet.write(row, 3, l[3], XLSX_STYLE['left'])
                worksheet.write(row, 4, l[4], XLSX_STYLE['right'])
                worksheet.write(row, 5, l[5], XLSX_STYLE['right'])
                worksheet.write(row, 6, l[6], XLSX_STYLE['left'])
                row += 1
            row += 1
        if self.footer:
            worksheet.write(row, 2, self.footer.strip(),
                            XLSX_STYLE['subtitle'])
            row += 2
        report.h = row
        return None

    def draw_text(self, report, f, xtn):
        """Write out a section in html."""
        if self.heading:
            f.write(htlib.h3(self.heading.strip(), {'id': self.sectionid}))
        if self.subheading:
            f.write(htlib.p(self.subheading.strip(), {'class': 'lead'}))
        if len(self.lines) > 0:
            rows = []
            if self.colheader:
                rows.append(self.colheader)
            for r in self.lines:
                nv = r[0:6]
                if len(nv) == 2:
                    nv = [nv[0], None, nv[1]]
                if len(nv) > 4:
                    # suppress the printrep underscores
                    nv[4] = ''
                rows.append(nv)
            trows = []
            for l in rows:
                trows.append(vec2htmlrow(l))
            f.write(
                htlib.table(htlib.tbody(trows), {'class': report.tablestyle}))
            f.write('\n')
        if self.footer:
            f.write(htlib.p(self.footer.strip()))
        return None


class bullet_text:
    """List of bullet items, each one a non-breaking pango para."""

    def __init__(self, secid=''):
        self.sectionid = secid
        self.status = None
        self.heading = None  # scalar
        self.subheading = None  # scalar
        self.footer = None
        self.units = None
        self.colheader = None
        self.lines = []  # list of sections: [bullet,para]
        self.lcount = 0  # last count of lines/len
        self.bullet = '\u2022'  # bullet type
        self.width = None  # allow override of width
        self.h = None  # computed height on page

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
            if self.width is None:  # override by caller allowed
                self.width = report.body_width - mm2pt(15 + 10)
            self.h = 0
            if self.heading:
                self.h += report.section_height
            if self.subheading:
                self.h += report.section_height
            if self.footer:
                self.h += report.line_height
            for line in self.lines:
                bh = report.line_height
                ph = 0
                if line[1] and report.p is not None:  # empty or none not drawn
                    ph = report.paragraph_height(line[1], self.width)
                self.h += max(bh, ph)  # enforce a minimum item height
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
        chk.lines = self.lines[0:1]  # minimum one item before break
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
            count = 1  # case: min one line before break
        while count < seclines:  # visit every item
            if ret.get_h(report) > remainder:
                # if overflow, undo last item and fall out to remainder
                rem.lines.append(ret.lines.pop(-1))
                break
            elif seclines - count <= 1:
                break  # hanging item check (rm=1)
            ret.lines.append(self.lines[count])
            count += 1
        while count < seclines:
            # collect all remainder items in rem
            rem.lines.append(self.lines[count])
            count += 1
        return (ret, rem)

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
            report.h += report.section_height
        if len(self.lines) > 0:
            if self.width is None:  # override by caller allowed
                self.width = report.body_width - mm2pt(15 + 10)
            for l in self.lines:
                bstr = self.bullet
                if l[0] is not None:
                    bstr = l[0]  # allow override even with ''
                # draw bullet
                bh = report.line_height  # minimum item height is one line
                if bstr:
                    report.text_left(report.body_left + mm2pt(5.0), report.h,
                                     bstr, report.fonts['body'])
                # draw para
                ph = 0
                if l[1]:  # allow empty list item
                    (pw, ph) = report.text_para(report.body_left + mm2pt(15.0),
                                                report.h, l[1],
                                                report.fonts['body'],
                                                self.width)
                report.h += max(ph, bh)
        if self.footer:
            report.text_cent(report.midpagew, report.h, self.footer,
                             report.fonts['subhead'])
            report.h += report.line_height
        report.c.restore()

    def draw_xlsx(self, report, worksheet):
        """Output program element to excel worksheet."""
        row = report.h
        if self.heading:
            worksheet.write(row, 2, self.heading.strip(), XLSX_STYLE['title'])
            row += 1
        if self.subheading:
            worksheet.write(row, 2, self.subheading.strip(),
                            XLSX_STYLE['subtitle'])
            row += 2
        else:
            row += 1
        if len(self.lines) > 0:
            for l in self.lines:
                oft = 0
                bstr = self.bullet
                if l[0]:
                    bstr = l[0]
                worksheet.write(row, 1, bstr,
                                XLSX_STYLE['left'])  # always one bullet
                istr = ''
                if l[1]:
                    istr = l[1]
                for line in istr.split('\n'):
                    worksheet.write(row + oft, 2, line, XLSX_STYLE['left'])
                    oft += 1
                row += max(oft, 1)
            row += 1
        report.h = row
        return None

    def draw_text(self, report, f, xtn):
        """Write out a section in html."""
        if self.heading:
            f.write(htlib.h3(self.heading.strip(), {'id': self.sectionid}))
        if self.subheading:
            f.write(htlib.p(self.subheading.strip(), {'class': 'lead'}))
        if len(self.lines) > 0:
            ol = []
            for l in self.lines:
                bstr = ''
                if l[0]:
                    bstr = '(' + l[0] + ') '
                if l[1]:
                    bstr += l[1]
                ol.append(htlib.li(bstr.rstrip()))
            f.write(htlib.ul(ol))
            f.write('\n')


class preformat_text:
    """Block of pre-formatted/monospaced plain text."""

    def __init__(self, secid=''):
        self.sectionid = secid
        self.status = None
        self.heading = None  # scalar
        self.subheading = None  # scalar
        self.colheader = None  # scalar
        self.footer = None
        self.units = None
        self.lines = []  # list of scalars
        self.lcount = 0  # last count of lines/len
        self.nobreak = False
        self.h = None  # computed height on page

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
            if self.colheader:  # colheader is written out with body
                cvec.append(self.colheader)
            self.h = report.preformat_height(cvec)
            if self.heading:
                self.h += report.section_height
            if self.subheading:
                self.h += report.section_height
            self.lcount = len(self.lines)
        return self.h

    def truncate(self, remainder, report):
        """Return a copy of the section up to page break."""

        # Special case 1: Entire section will fit on page
        if self.get_h(report) <= (remainder + report.page_overflow):
            return (self, None)

        # Special case: Don't break if possible
        if self.nobreak and report.pagefrac() > FEPSILON:
            # move entire section onto next page
            return (pagebreak(0.01), self)

        # Special case 2: Not enough space for minimum content
        chk = preformat_text()
        chk.heading = self.heading
        chk.subheading = self.subheading
        chk.colheader = self.colheader
        if len(self.lines) == 3:  # special case, keep 'threes' together
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
            count = 1  # case: 3 lines broken on first line
        while count < seclines:  # case: push min two lines over break
            if ret.get_h(report) > remainder:
                # pop last line onto rem and break
                rem.lines.append(ret.lines.pop(-1))
                break
            elif seclines - count <= 2:  # push min 2 lines over to next page
                break
            ret.lines.append(self.lines[count])
            count += 1
        while count < seclines:
            rem.lines.append(self.lines[count])
            count += 1
        return (ret, rem)

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
            report.h += report.section_height
        if len(self.lines) > 0:
            rows = []
            if self.colheader:
                rows.append(self.colheader)
            rows.extend(self.lines)
            ust = '\n'.join(rows)
            (w, h) = report.text_cent(report.midpagew,
                                      report.h,
                                      ust,
                                      report.fonts['monospace'],
                                      halign=Pango.Alignment.LEFT)
            report.h += h
        report.c.restore()

    def draw_xlsx(self, report, worksheet):
        """Output program element to excel worksheet."""
        row = report.h
        if self.heading:
            worksheet.write(row, 2, self.heading.strip(), XLSX_STYLE['title'])
            row += 1
        if self.subheading:
            worksheet.write(row, 2, self.subheading.strip(),
                            XLSX_STYLE['subtitle'])
            row += 2
        else:
            row += 1
        if len(self.lines) > 0:
            if self.colheader:
                worksheet.write(row, 2, self.colheader,
                                XLSX_STYLE['monospace'])
                row += 1
            for l in self.lines:
                worksheet.write(row, 2, l.rstrip(), XLSX_STYLE['monospace'])
                row += 1
            row += 1
        report.h = row
        return None

    def draw_text(self, report, f, xtn):
        """Write out a section in html."""
        if self.heading:
            f.write(htlib.h3(self.heading.strip(), {'id': self.sectionid}))
        if self.subheading:
            f.write(htlib.p(self.subheading.strip(), {'class': 'lead'}))
        if len(self.lines) > 0:
            prelines = []
            if self.colheader:
                prelines.append(self.colheader.rstrip())
            for row in self.lines:
                prelines.append(row.rstrip())
            f.write(htlib.pre('\n'.join(prelines)))


class event_index:
    """Copy of plain section, but in text output text links."""

    def __init__(self, secid=''):
        self.sectionid = secid
        self.status = None
        self.heading = None  # scalar
        self.colheader = None  # scalar
        self.subheading = None  # scalar
        self.footer = None
        self.units = None  # scalar
        self.lines = []  # list of column lists
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
            # Set an estimate h for json export with no pdf
            self.h = report.line_height * len(self.lines)
            if self.colheader:  # colheader is written out with body
                self.h += report.line_height
                cvec.append(['-', '-', '-', '-', '-', '-'])
            if self.heading:
                self.h += report.section_height
            if self.subheading:
                self.h += report.section_height
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
        if len(self.lines) == 3:  # special case, keep 'threes' together
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
            count = 1  # case: 3 lines broken on first line
        while count < seclines:  # case: push min two lines over break
            if ret.get_h(report) > remainder:
                # pop last line onto rem and break
                rem.lines.append(ret.lines.pop(-1))
                break
            elif seclines - count <= 2:  # push min 2 lines over to next page
                break
            ret.lines.append(self.lines[count])
            count += 1
        while count < seclines:
            rem.lines.append(self.lines[count])
            count += 1
        return (ret, rem)

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
            report.h += report.section_height
        if len(self.lines) > 0:
            rows = []
            if self.colheader:
                rows.append(self.colheader)
            rows.extend(self.lines)
            # just hard-code cols for now, later do a colspec?
            if self.units:
                ust = self.units
                if self.colheader:
                    ust = '\n' + ust
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

    def draw_xlsx(self, report, worksheet):
        """Output program element to excel worksheet."""
        row = report.h
        if self.heading:
            worksheet.write(row, 2, self.heading.strip(), XLSX_STYLE['title'])
            row += 1
        if self.subheading:
            worksheet.write(row, 2, self.subheading.strip(),
                            XLSX_STYLE['subtitle'])
            row += 2
        else:
            row += 1
        if len(self.lines) > 0:
            rows = []
            if self.colheader:
                rows.append(vecmapstr(self.colheader, 7))
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
                worksheet.write(row, 0, l[0], XLSX_STYLE['left'])
                #worksheet.write(row, 1, l[1], XLSX_STYLE['right'])
                worksheet.write(row, 2, l[2], XLSX_STYLE['left'])
                worksheet.write(row, 3, l[3], XLSX_STYLE['left'])
                #worksheet.write(row, 4, l[4], XLSX_STYLE['right'])
                #worksheet.write(row, 5, l[5], XLSX_STYLE['right'])
                #worksheet.write(row, 6, l[6], XLSX_STYLE['left'])
                row += 1
            row += 1
        report.h = row
        return None

    def draw_text(self, report, f, xtn):
        """Write out a section in html."""
        if self.heading:
            f.write(htlib.h3(self.heading.strip(), {'id': self.sectionid}))
        if self.subheading:
            f.write(htlib.p(self.subheading.strip(), {'class': 'lead'}))

        if len(self.lines) > 0:
            hdr = ''
            if self.colheader:
                _log.warning('Colheader not supported for %s',
                             self.__class__.__name__)
                #hdr = htlib.thead(vec2htmllinkhead(self.colheader))
            rows = []
            for r in self.lines:
                nv = r[0:7]
                if len(nv) == 2:
                    nv = [nv[0], None, nv[1]]
                rows.append(nv)
            if self.units:
                rows[0].append(self.units)
            trows = []
            for l in rows:
                trows.append(vec2htmllinkrow(l, xtn, report))
            f.write(
                htlib.table((hdr, htlib.tbody(trows)),
                            {'class': report.tablestyle}))
        return None


class laptimes:
    """Section for display of lap times/splits"""

    def __init__(self, secid='laptimes'):
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
        self.nobreak = False
        self.start = None
        self.finish = None
        self.laptimes = None
        self.precision = 0

    def serialize(self, rep, sectionid=None):
        """Return a serializable map for JSON export."""
        ret = {}
        ret['sectionid'] = sectionid
        ret['type'] = 'laptimes'
        ret['heading'] = self.heading
        ret['status'] = self.status
        ret['subheading'] = self.subheading
        ret['colheader'] = self.colheader
        ret['footer'] = self.footer
        ret['units'] = self.units
        ret['lines'] = self.lines
        ret['height'] = self.get_h(rep)
        ret['count'] = self.lcount
        ret['precision'] = self.precision
        ret['start'] = self.start
        ret['finish'] = self.finish
        return ret

    def get_h(self, report):
        """Return total height on page of section on report."""
        if self.h is None or len(self.lines) != self.lcount:
            self.lcount = len(self.lines)
            self.h = report.line_height * self.lcount
            if self.colheader:  # colheader is written out with body
                self.h += report.line_height
            if self.heading:
                self.h += report.section_height
            if self.subheading:
                self.h += report.section_height
            if self.footer:
                self.h += report.line_height
        return self.h

    def truncate(self, remainder, report):
        """Return a copy of the section up to page break."""

        # Special case: Entire section will fit on page
        if self.get_h(report) <= (remainder + report.page_overflow):
            return (self, None)

        # Special case: Don't break if possible
        if self.nobreak and report.pagefrac() > FEPSILON:
            # move entire section onto next page
            return (pagebreak(0.01), self)

        # Special case: Not enough space for minimum content
        chk = laptimes()
        chk.heading = self.heading
        chk.subheading = self.subheading
        chk.colheader = self.colheader
        chk.footer = self.footer
        chk.units = self.units
        chk.start = self.start
        chk.finish = self.finish
        chk.precision = self.precision
        chk.laptimes = self.laptimes
        if len(self.lines) <= 4:  # special case, keep four or less together
            chk.lines = self.lines[0:]
        else:  # BUT, don't break before third rider
            chk.lines = self.lines[0:2]
        if chk.get_h(report) > remainder:
            # move entire section onto next page
            return (pagebreak(), self)

        # Standard case - section crosses page break, determines
        # ret: content on current page
        # rem: content on subsequent pages
        ret = laptimes()
        rem = laptimes()
        ret.heading = self.heading
        ret.subheading = self.subheading
        ret.colheader = self.colheader
        ret.footer = self.footer
        ret.units = self.units
        ret.start = self.start
        ret.finish = self.finish
        ret.precision = self.precision
        ret.laptimes = self.laptimes
        rem.heading = self.heading
        rem.subheading = self.subheading
        rem.colheader = self.colheader
        rem.footer = self.footer
        rem.units = self.units
        rem.start = self.start
        rem.finish = self.finish
        rem.precision = self.precision
        rem.laptimes = self.laptimes
        if rem.heading is not None:
            if rem.heading.rfind('(continued)') < 0:
                rem.heading += ' (continued)'
        seclines = len(self.lines)
        count = 0
        if seclines > 0:
            while count < seclines and count < 3:  # don't break until 3rd
                ret.lines.append(self.lines[count])
                count += 1
        while count < seclines:
            if ret.get_h(report) > remainder:
                # pop last line onto rem and break
                rem.lines.append(ret.lines.pop(-1))
                break
            elif seclines - count <= 2:  # push min 2 names over to next page
                break
            ret.lines.append(self.lines[count])
            count += 1
        while count < seclines:
            rem.lines.append(self.lines[count])
            count += 1
        return (ret, rem)

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
            report.h += report.section_height
        cnt = 0

        if len(self.lines) > 0:
            report.h += report.judges_row(
                report.h, (self.colheader[0], self.colheader[1],
                           self.colheader[2], 'lap', 'avg', 'best', 'cat'))
            starth = report.h
            cnt = 0
            for r in self.lines:
                # TEMP: unwrap lap times into absolute for display
                bestt = tod.MAX
                if r['laps'] and self.start is not None:
                    ftoft = None
                    stoft = tod.ZERO
                    curlap = stoft
                    if r['start'] is not None:
                        ftoft = self.finish - self.start
                        curlap += r['start'] - self.start
                    rlaps = []
                    for l in r['laps']:
                        if l < bestt:
                            bestt = l
                        curlap = curlap + l
                        rlaps.append(curlap)
                    report.laplines(report.h, rlaps, stoft, ftoft)
                plstr = r['place']
                placed = False
                if plstr:
                    placed = True
                    if plstr.isdigit():
                        plstr += '.'

                ravg = ''
                if r['average'] is not None:
                    ravg = r['average'].rawtime(self.precision)

                beststr = ''
                if bestt < tod.MAX:  # one time at least was found
                    beststr = bestt.rawtime(self.precision)
                lr = (
                    plstr,  # 0 rank/place
                    r['no'],  # 1 rider no
                    r['name'],  # 2  name
                    str(r['count']),  # 3 lap count
                    ravg,  # 4 time
                    beststr,  # 5 xtra
                    None,  # 6 n/a
                    placed,  # 7 placed?
                    False,  # 8 photofinish?
                    None,  # 9 n/a
                    r['cat'],  # 10 cat
                    None,  # 11 n/a
                )
                report.h += report.judges_row(report.h, lr, cnt % 2)
                cnt += 1
            # do laplines like on judgerep
            endh = report.h  # - for the column shade box
            if self.start is not None and self.laptimes is not None and len(
                    self.laptimes) > 0:
                report.laplines(starth,
                                self.laptimes,
                                self.start,
                                self.finish,
                                endh=endh,
                                reverse=True)
            report.drawbox(report.col_oft_time - mm2pt(15.0), starth,
                           report.col_oft_time + mm2pt(1.0), endh, 0.07)
        if self.footer:
            report.text_cent(report.midpagew, report.h, self.footer,
                             report.fonts['subhead'])
            report.h += report.line_height
        report.c.restore()

    def draw_xlsx(self, report, worksheet):
        """Output program element to excel worksheet."""
        # Note: Excel time format is in units of one day, this
        #       export sends the truncated timeval divided by
        #       86400, with a time format to match the desired tod
        #       precision, eg: [m]:ss.00 for precision 2
        row = report.h
        if self.heading:
            worksheet.write(row, 2, self.heading.strip(), XLSX_STYLE['title'])
            row += 1
        if self.subheading:
            worksheet.write(row, 2, self.subheading.strip(),
                            XLSX_STYLE['subtitle'])
            row += 2
        else:
            row += 1
        if len(self.lines) > 0:
            wsstyle = XLSX_STYLE['laptime0']
            if self.precision == 3:
                wsstyle = XLSX_STYLE['laptime3']
            if self.precision == 2:
                wsstyle = XLSX_STYLE['laptime2']
            elif self.precision == 1:
                wsstyle = XLSX_STYLE['laptime1']

            if self.colheader:
                # rank col is skipped for laptime report
                headlen = len(self.colheader)
                headrow = vecmapstr(self.colheader, maxkey=headlen)
                worksheet.write(row, 1, headrow[0], XLSX_STYLE['right'])
                worksheet.write(row, 2, headrow[1], XLSX_STYLE['left'])
                worksheet.write(row, 3, headrow[2], XLSX_STYLE['left'])
                worksheet.write(row, 4, headrow[3], XLSX_STYLE['right'])
                for col in range(4, headlen):
                    worksheet.write(row, col + 1, headrow[col],
                                    XLSX_STYLE['right'])
                row += 1
            for r in self.lines:
                worksheet.write(row, 1, r['no'], XLSX_STYLE['right'])
                worksheet.write(row, 2, r['name'], XLSX_STYLE['left'])
                worksheet.write(row, 3, r['cat'], XLSX_STYLE['left'])
                worksheet.write(row, 4, r['count'], XLSX_STYLE['right'])
                if r['average'] is not None:
                    worksheet.write(row, 5, r['average'].timeval / 86400,
                                    wsstyle)
                col = 6
                for lap in r['laps']:
                    worksheet.write(row, col, lap.timeval / 86400, wsstyle)
                    col += 1
                if r['place'] and not r['place'].isdigit():
                    worksheet.write(row, col, r['place'], XLSX_STYLE['right'])
                row += 1
            row += 1
        if self.footer:
            worksheet.write(row, 2, self.footer.strip(),
                            XLSX_STYLE['subtitle'])
            row += 2
        report.h = row
        return None

    def draw_text(self, report, f, xtn):
        """Write out a section in html."""
        if self.heading:
            f.write(htlib.h3(self.heading.strip(), {'id': self.sectionid}))
        if self.subheading:
            f.write(htlib.p(self.subheading.strip(), {'class': 'lead'}))

        if len(self.lines) > 0:
            hdr = ''
            hlen = 7  # ensure at least this many columns in table
            if self.colheader:
                hlen = max(7, len(self.colheader))
                hdr = htlib.thead(vec2htmlhead(self.colheader, maxcol=hlen))
            trows = []
            for r in self.lines:
                nr = [
                    r['no'],
                    r['name'],
                    r['cat'],
                    str(r['count']),
                ]
                if r['average'] is not None:
                    nr.append(r['average'].rawtime(self.precision))
                else:
                    nr.append(None)
                for l in r['laps']:
                    nr.append(l.rawtime(self.precision))
                if r['place'] and not r['place'].isdigit():
                    nr.append(r['place'])
                trows.append(vec2htmlrow(nr, maxcol=hlen))
            f.write(
                htlib.div(
                    htlib.table((hdr, htlib.tbody(trows)),
                                {'class': report.tablestyle}),
                    {'class': 'table-responsive'}))
            f.write('\n')
        if self.footer:
            f.write(htlib.p(self.footer.strip()))
        return None


class judgerep:

    def __init__(self, secid=''):
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
        ret['type'] = 'judgerep'
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
            if self.colheader:  # colheader is written out with body
                self.h += report.line_height
            if self.heading:
                self.h += report.section_height
            if self.subheading:
                self.h += report.section_height
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
        if len(self.lines) <= 4:  # special case, keep four or less together
            chk.lines = self.lines[0:]
        else:  # BUT, don't break before third rider
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
            while count < seclines and count < 3:  # don't break until 3rd
                ret.lines.append(self.lines[count])
                count += 1
        while count < seclines:
            if ret.get_h(report) > remainder:
                # pop last line onto rem and break
                rem.lines.append(ret.lines.pop(-1))
                break
            elif seclines - count <= 2:  # push min 2 names over to next page
                break
            ret.lines.append(self.lines[count])
            count += 1
        while count < seclines:
            rem.lines.append(self.lines[count])
            count += 1
        return (ret, rem)

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
            report.h += report.section_height
        cnt = 0
        if len(self.lines) > 0:
            if self.colheader:
                #report.h += report.judges_row(report.h, self.colheader)
                report.h += report.judges_row(
                    report.h, (self.colheader[0], self.colheader[1],
                               self.colheader[2], 'lap', '', 'avg'))
            sh = report.h
            if self.units:
                report.text_left(report.col_oft_units, report.h, self.units,
                                 report.fonts['body'])
            st = tod.mktod(self.start)
            ft = tod.mktod(self.finish)
            if ft is None and st is not None:
                ft = tod.now()
            for r in self.lines:
                lstart = st
                # TEMP: until laplines fixed in cross/rms/circuit
                #if len(r) > 9 and r[9] is not None:
                #lstart = tod.mktod(r[9])
                lfinish = ft
                if len(r) > 11 and r[11] is not None:
                    lfinish = tod.mktod(r[11])
                if len(r) > 6 and r[6] is not None and len(
                        r[6]) > 0 and lstart is not None:
                    report.laplines(report.h, r[6], lstart, lfinish)
                report.h += report.judges_row(report.h, r, cnt % 2)
                cnt += 1
            eh = report.h  # - for the column shade box
            if st is not None and self.laptimes is not None and len(
                    self.laptimes) > 0:
                report.laplines(sh,
                                self.laptimes,
                                st,
                                ft,
                                endh=eh,
                                reverse=True)
            report.drawbox(report.col_oft_time - mm2pt(15.0), sh,
                           report.col_oft_time + mm2pt(1.0), eh, 0.07)
        if self.footer:
            report.text_cent(report.midpagew, report.h, self.footer,
                             report.fonts['subhead'])
            report.h += report.line_height
        report.c.restore()

    def draw_xlsx(self, report, worksheet):
        """Output program element to excel worksheet."""
        row = report.h
        if self.heading:
            worksheet.write(row, 2, self.heading.strip(), XLSX_STYLE['title'])
            row += 1
        if self.subheading:
            worksheet.write(row, 2, self.subheading.strip(),
                            XLSX_STYLE['subtitle'])
            row += 2
        else:
            row += 1
        if len(self.lines) > 0:
            if self.colheader:
                headlen = max(7, len(self.colheader))

                headrow = vecmapstr(self.colheader, maxkey=headlen)
                worksheet.write(row, 0, headrow[0], XLSX_STYLE['left'])
                worksheet.write(row, 1, headrow[1], XLSX_STYLE['right'])
                worksheet.write(row, 2, headrow[2], XLSX_STYLE['left'])
                worksheet.write(row, 3, headrow[3], XLSX_STYLE['left'])
                for col in range(4, headlen):
                    worksheet.write(row, col, headrow[col],
                                    XLSX_STYLE['right'])
                row += 1
            revoft = row
            rows = []
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
                st = tod.ZERO
                if self.start is not None:
                    st = tod.mktod(self.start)
                worksheet.write(row, 0, l[0], XLSX_STYLE['left'])
                worksheet.write(row, 1, l[1], XLSX_STYLE['right'])
                worksheet.write(row, 2, l[2], XLSX_STYLE['left'])
                worksheet.write(row, 3, l[3], XLSX_STYLE['left'])
                worksheet.write(row, 4, l[4], XLSX_STYLE['right'])
                worksheet.write(row, 5, l[5], XLSX_STYLE['right'])
                #worksheet.write(row, 6, l[6], XLSX_STYLE['left'])
                srow = row - revoft
                if srow >= 0:
                    srcl = self.lines[srow]
                    if len(srcl) > 9 and srcl[9] is not None:
                        catStart = tod.mktod(srcl[9])
                        if catStart is not None:
                            # add a category start offset
                            st += catStart
                    if len(srcl) > 10 and srcl[10]:
                        # show cat label in units col
                        worksheet.write(row, 6, srcl[10], XLSX_STYLE['left'])
                    if len(srcl) > 6 and srcl[6] is not None and len(
                            srcl[6]) > 0:
                        # append each lap time to row
                        llt = st
                        roft = 7
                        for k in srcl[6]:
                            kt = tod.mktod(k)
                            if kt is not None:
                                worksheet.write(row, roft,
                                                (kt - llt).rawtime(1),
                                                XLSX_STYLE['right'])
                                llt = kt
                                roft += 1
                row += 1
            row += 1
        if self.footer:
            worksheet.write(row, 2, self.footer.strip(),
                            XLSX_STYLE['subtitle'])
            row += 2
        report.h = row
        return None

    def draw_text(self, report, f, xtn):
        """Write out a section in html."""
        if self.heading:
            f.write(htlib.h3(self.heading.strip(), {'id': self.sectionid}))
        if self.subheading:
            f.write(htlib.p(self.subheading.strip(), {'class': 'lead'}))

        if len(self.lines) > 0:
            hdr = ''
            if self.colheader:
                hdr = htlib.thead(
                    vec2htmlhead(self.colheader,
                                 maxcol=max(7, len(self.colheader))))
            rows = []
            for r in self.lines:
                rcat = ''
                lcnt = ''
                lts = []
                st = tod.ZERO
                if self.start is not None:
                    st = tod.mktod(self.start)
                if len(r) > 9 and r[9] is not None:
                    catStart = tod.mktod(r[9])
                    if catStart is not None:
                        # add a category start offset
                        st += catStart
                if len(r) > 10 and r[10]:
                    rcat = r[10]
                if len(r) > 3 and r[3]:
                    lcnt = r[3]
                if len(r) > 6 and r[6] is not None and len(r[6]) > 0:
                    # append each lap time to row
                    llt = st
                    for k in r[6]:
                        kt = tod.mktod(k)
                        if kt is not None:
                            lts.append((kt - llt).rawtime(1))
                            llt = kt
                nv = r[0:6]
                if len(nv) == 2:
                    nv = [nv[0], None, nv[1]]
                else:
                    if len(nv) > 3:
                        nv[3] = rcat
                    if len(nv) > 4:
                        nv[4] = lcnt
                    if len(nv) == 6:
                        if lts:
                            nv.extend(lts)
                rows.append(nv)
            #if self.units:
            #rows[0].append(self.units)
            trows = []
            for l in rows:
                trows.append(vec2htmlrow(l, maxcol=max(7, len(l))))
            f.write(
                htlib.div(
                    htlib.table((hdr, htlib.tbody(trows)),
                                {'class': report.tablestyle}),
                    {'class': 'table-responsive'}))
            f.write('\n')
        if self.footer:
            f.write(htlib.p(self.footer.strip()))
        return None


class teampage:
    """One-page teams race startlist, with individuals in 3 columns."""

    def __init__(self, secid=''):
        self.sectionid = secid
        self.heading = None
        self.status = None
        self.subheading = None
        self.colheader = None
        self.units = None
        self.footer = None
        self.lines = []
        self.teammap = {}
        self.expand = 0.0  # extra space between teams
        self.scale = 1.0  # scale line height localy if required
        self.lcount = 0
        self.height = None  # override height on page
        self.h = None

    def serialize(self, rep, sectionid=None):
        """Return a serializable map for JSON export."""
        ret = {}
        ret['sectionid'] = sectionid
        ret['type'] = 'teampage'
        ret['heading'] = self.heading
        ret['status'] = self.status
        ret['subheading'] = self.subheading
        ret['colheader'] = self.colheader
        ret['footer'] = self.footer
        ret['units'] = self.units
        ret['lines'] = self.lines
        ret['teammap'] = self.teammap
        ret['height'] = self.get_h(rep)
        ret['count'] = self.lcount
        return ret

    def set_height(self, newh=None):
        """Override height to a set value string."""
        if newh is not None:
            self.height = str2len(newh)

    def get_h(self, report):
        """Return total height on page of section on report."""
        if self.h is None or len(self.lines) != self.lcount:
            self.lcount = len(self.lines)
            if self.height is None:
                self.height = report.body_len  # default to whole page
            self.h = self.height
        return self.h

    def truncate(self, remainder, report):
        """Move onto next page or raise exception."""
        if self.get_h(report) <= (remainder + report.page_overflow):
            return (self, None)
        else:
            if report.pagefrac() < FEPSILON:
                raise RuntimeWarning(
                    'Section ' + repr(self.heading) +
                    ' will not fit on a page and will not break.')
            # move entire section onto next page
            return (pagebreak(), self)

    def draw_pdf(self, report):
        """Output a one-page teams list."""
        report.c.save()
        glen = self.h
        rcount = 0
        if self.heading:
            report.text_cent(report.midpagew, report.h, self.heading,
                             report.fonts['section'])
            report.h += report.section_height
            glen -= report.section_height
        if self.subheading:
            report.text_cent(report.midpagew, report.h, self.subheading,
                             report.fonts['subhead'])
            report.h += report.section_height
            glen -= report.section_height
        if self.footer:
            glen -= report.line_height

        localline = self.scale * report.line_height
        if self.lcount > 0:
            col = 0
            pageoft = report.h
            endpage = report.h + glen
            tcw = mm2pt(5.0)
            tnw = report.col3_width - tcw
            for t in self.lines:
                tname = t[2]
                if t[1]:
                    tname += ' (' + t[1] + ')'
                tnat = t[3]
                tnh = localline
                fnh = report.teamname_height(tname, report.col3_width)
                # now search for a better width:
                tnoft = 0
                tnwidth = report.col3_width
                while tnwidth > 1.0:
                    tnwidth -= mm2pt(0.2)
                    tnoft += mm2pt(0.1)
                    chh = report.teamname_height(tname, tnwidth)
                    if (chh - fnh) > FEPSILON:
                        tnwidth += mm2pt(0.2)
                        tnoft -= mm2pt(0.1)
                        break

                tnh = max(tnh, fnh)
                th = self.scale * tnh
                ds = None
                dat = None
                if t[1] in self.teammap:
                    dat = self.teammap[t[1]]
                    if 'ds' in dat and dat['ds']:
                        th += localline
                        ds = dat['ds']
                    th += len(dat['riders']) * report.line_height
                # space left in column?
                if pageoft + th > endpage:  # would have overflowed
                    pageoft = report.h
                    col += 1
                    if col > 2:
                        col = 2
                # draw code/name
                left = report.col3t_loft[col]
                if tname:
                    report.text_para(left + tnoft, pageoft, tname,
                                     report.fonts['section'], tnwidth,
                                     Pango.Alignment.CENTER)
                #if tcode:
                #tco = pageoft
                #if tnh > localline:
                #tco += 0.5 * (tnh - localline)
                #report.text_right(left + tcw - mm2pt(1.0), tco, tcode, report.fonts[u'section'])
                pageoft += self.scale * tnh
                #pageoft += 0.9 * tnh

                # optionally draw ds
                if ds is not None:
                    report.text_cent(left + tnoft + 0.5 * tnwidth, pageoft,
                                     'DS: ' + ds, report.fonts['body'])
                    pageoft += localline
                # draw riders
                rnw = tnw - tcw - mm2pt(1.0)
                for r in dat['riders']:
                    strike = False
                    report.text_right(left + tcw - mm2pt(1.0), pageoft, r[1],
                                      report.fonts['body'])
                    report.fit_text(left + tcw,
                                    pageoft,
                                    r[2],
                                    rnw,
                                    font=report.fonts['body'])
                    report.text_left(left + tnw, pageoft, r[3],
                                     report.fonts['body'])
                    if r[0]:
                        report.drawline(left + mm2pt(0.5),
                                        pageoft + (0.5 * localline),
                                        left + report.col3_width - mm2pt(0.5),
                                        pageoft + (0.5 * localline))
                    rcount += 1
                    pageoft += localline
                pageoft += report.line_height + self.expand
            # place each team in the order delivered.

        # advance report.h to end of page
        report.h += glen
        if self.footer or rcount > 0:
            mv = []
            if rcount > 0:
                mv.append('{} starters.'.format(rcount))
            if self.footer:
                mv.append(self.footer)
            msg = '\u2003'.join(mv)
            report.text_cent(report.midpagew, report.h, msg,
                             report.fonts['subhead'])
            report.h += report.line_height
        report.c.restore()

    def draw_xlsx(self, report, worksheet):
        """Output program element to excel worksheet."""
        row = report.h
        if self.heading:
            worksheet.write(row, 2, self.heading.strip(), XLSX_STYLE['title'])
            row += 1
        if self.subheading:
            worksheet.write(row, 2, self.subheading.strip(),
                            XLSX_STYLE['subtitle'])
            row += 2
        else:
            row += 1
        if len(self.lines) > 0:
            for t in self.lines:
                worksheet.write(row, 1, t[1], XLSX_STYLE['title'])
                worksheet.write(row, 2, t[2], XLSX_STYLE['title'])
                worksheet.write(row, 3, t[3], XLSX_STYLE['left'])
                row += 1
                if t[1] in self.teammap:
                    dat = self.teammap[t[1]]
                    if 'ds' in dat and dat['ds']:
                        worksheet.write(row, 1, 'DS:', XLSX_STYLE['right'])
                        worksheet.write(row, 2, dat['ds'], XLSX_STYLE['left'])
                        row += 1
                    rows = []
                    for r in dat['riders']:
                        nv = r[0:6]
                        if len(nv) == 2:
                            nv = [nv[0], None, nv[1]]
                        rows.append(vecmapstr(nv, 7))
                    for l in rows:
                        worksheet.write(row, 0, l[0], XLSX_STYLE['left'])
                        worksheet.write(row, 1, l[1], XLSX_STYLE['right'])
                        worksheet.write(row, 2, l[2], XLSX_STYLE['left'])
                        worksheet.write(row, 3, l[3], XLSX_STYLE['left'])
                        worksheet.write(row, 4, l[4], XLSX_STYLE['right'])
                        worksheet.write(row, 5, l[5], XLSX_STYLE['right'])
                        worksheet.write(row, 6, l[6], XLSX_STYLE['left'])
                        row += 1
                row += 1
        if self.footer:
            worksheet.write(row, 2, self.footer.strip(),
                            XLSX_STYLE['subtitle'])
            row += 2
        report.h = row
        return None

    def draw_text(self, report, f, xtn):
        """Write out a section in html."""
        # These are not normally output on team page - but left as option
        if self.heading:
            f.write(htlib.h3(self.heading.strip(), {'id': self.sectionid}))
        if self.subheading:
            f.write(htlib.p(self.subheading.strip(), {'class': 'lead'}))
        if self.footer:
            f.write(htlib.p(htlib.small(self.footer.strip())))
        rcount = 0
        if len(self.lines) > 0:
            for t in self.lines:
                f.write(
                    htlib.h3(
                        (htlib.span(t[1],
                                    {'class': 'badge bg-primary'}), t[2])))
                if t[1] in self.teammap:
                    dat = self.teammap[t[1]]
                    if 'ds' in dat and dat['ds']:
                        f.write(htlib.p('DS: ' + dat['ds']))
                    rows = []
                    for r in dat['riders']:
                        nv = r[0:6]
                        if len(nv) == 2:
                            nv = [nv[0], None, nv[1]]
                        rcount += 1
                        rows.append(nv)
                    trows = []
                    for l in rows:
                        trows.append(vec2htmlrow(l))
                    f.write(
                        htlib.table(htlib.tbody(trows),
                                    {'class': report.tablestyle}))
                    f.write('\n')
        if rcount > 0:
            f.write(htlib.p(htlib.small('{} starters.'.format(rcount))))
        return None


class gamut:
    """Whole view of the entire tour - aka crossoff."""

    def __init__(self, secid=''):
        self.sectionid = secid
        self.heading = None
        self.status = None
        self.subheading = None
        self.colheader = None
        self.units = None
        self.footer = None
        self.lines = []
        self.cellmap = {}
        self.maxcol = 9  # depends on tour
        self.minaspect = 2.0  # minimum ratio to retain
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
            self.h = report.body_len  # section always fills page
        return self.h

    def truncate(self, remainder, report):
        """Move onto next page or raise exception."""
        if self.get_h(report) <= (remainder + report.page_overflow):
            return (self, None)
        else:
            if report.pagefrac() < FEPSILON:
                raise RuntimeWarning(
                    'Section ' + repr(self.heading) +
                    ' will not fit on a page and will not break.')
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
            report.h += report.section_height
            glen -= report.section_height
        if self.footer:
            glen -= report.line_height

        if self.lcount > 0:
            # determine geometry
            lmargin = report.body_left + mm2pt(0.25) - mm2pt(10.0)
            rmargin = report.body_right + mm2pt(10.0)
            if self.maxcol < 6:  # increase margins for teams of 6
                lmargin += mm2pt(10.0)
                rmargin -= mm2pt(10.0)
            elif self.maxcol > 8:  # decrease margins for teams of 8
                lmargin -= mm2pt(10.0)
                rmargin += mm2pt(10.0)
            pwidth = rmargin - lmargin
            cwidth = pwidth / self.maxcol
            cheight = glen / self.lcount
            caspect = cwidth / cheight
            if caspect < self.minaspect:
                cheight = cwidth / self.minaspect
            fnsz = cheight * 0.35
            gfonts = {}
            gfonts['key'] = Pango.FontDescription(report.gamutstdfont + ' ' +
                                                  str(fnsz))
            fnsz = cheight * 0.13
            gfonts['text'] = Pango.FontDescription(report.gamutobfont + ' ' +
                                                   str(fnsz))
            fnsz = cheight * 0.20
            gfonts['gcline'] = Pango.FontDescription(report.gamutobfont + ' ' +
                                                     str(fnsz))
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
                        report.gamut_cell(report.h, colof, cheight, cwidth, c,
                                          alph, gfonts, cmap)
                    colof += cwidth
                if alph == al:
                    alph = ad
                else:
                    alph = al
                report.h += cheight


# divide up and then enforce aspect limits
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
        # advance report.h to end of page
        report.c.restore()

    def draw_xlsx(self, report, worksheet):
        """Output program element to excel worksheet."""
        return None  # SKIP on xls
        row = report.h
        if self.heading:
            worksheet.write(row, 2, self.heading.strip(), XLSX_STYLE['title'])
            row += 1
        if self.subheading:
            worksheet.write(row, 2, self.subheading.strip(),
                            XLSX_STYLE['subtitle'])
            row += 2
        else:
            row += 1
        if len(self.lines) > 0:
            pass
        if self.footer:
            worksheet.write(row, 2, self.footer.strip(),
                            XLSX_STYLE['subtitle'])
            row += 2
        report.h = row
        return None

    def draw_text(self, report, f, xtn):
        """Write out a section in html."""
        return None  # Skip section on web output
        if self.heading:
            f.write(htlib.h3(self.heading.strip(), {'id': self.sectionid}))
        if self.subheading:
            f.write(htlib.p(self.subheading.strip(), {'class': 'lead'}))

        if len(self.lines) > 0:
            pass
        if self.footer:
            f.write(htlib.p(self.footer.strip()))
        return None


class threecol_section:

    def __init__(self, secid=''):
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
        ret['type'] = 'threecol'
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
            self.h = report.line_height * int(math.ceil(self.lcount / 3.0))
            if self.colheader:  # colheader is written out with body
                self.h += report.line_height
            if self.heading:
                self.h += report.section_height
            if self.subheading:
                self.h += report.section_height
            if self.footer:
                self.h += report.line_height
        return self.h

    def truncate(self, remainder, report):
        """Return a copy of the section up to page break."""

        # Special case 1: Entire section will fit on page
        if self.get_h(report) <= (remainder + report.page_overflow):
            return (self, None)

        # Special case 2: Not enough space for minimum content
        chk = threecol_section()
        chk.heading = self.heading
        chk.subheading = self.subheading
        chk.colheader = self.colheader
        chk.footer = self.footer
        chk.units = self.units
        if len(self.lines) <= 6:  # special case, keep 2 lines of 3
            chk.lines = self.lines[0:]
        else:  # BUT, don't break before third rider
            chk.lines = self.lines[0:6]
        if chk.get_h(report) > remainder:
            # move entire section onto next page
            return (pagebreak(), self)

        # Standard case - section crosses page break, determines
        # ret: content on current page
        # rem: content on subsequent pages
        ret = threecol_section()
        rem = threecol_section()
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
            while count < seclines and count < 6:  # don't break until 6th
                ret.lines.append(self.lines[count])
                count += 1
        while count < seclines:
            if ret.get_h(report) > remainder:
                # pop last line onto rem and break
                rem.lines.append(ret.lines.pop(-1))
                break
            elif seclines - count <= 6:  # push min 6 names over to next page
                break
            ret.lines.append(self.lines[count])
            count += 1
        while count < seclines:
            rem.lines.append(self.lines[count])
            count += 1
        return (ret, rem)

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
            report.h += report.section_height
        cnt = 0
        if len(self.lines) > 0:
            if self.colheader:
                report.h += report.standard_3row(report.h, self.colheader,
                                                 self.colheader,
                                                 self.colheader)
            #sh = report.h
            #if self.units:	# NO UNITS?
            #report.text_left(report.col_oft_units, report.h, self.units,
            #report.fonts[u'body'])
        #    lcount
            lcount = int(math.ceil(self.lcount / 3.0))
            for l in range(0, lcount):
                r1 = self.lines[l]
                r2 = None
                if len(self.lines) > l + lcount:
                    r2 = self.lines[l + lcount]  # for degenerate n<5
                r3 = None
                if len(self.lines) > l + lcount + lcount:
                    r3 = self.lines[l + lcount + lcount]
                grey = 0
                if self.grey:
                    grey = (l) % 2
                report.h += report.standard_3row(report.h, r1, r2, r3, grey)
        if self.footer:
            report.text_cent(report.midpagew, report.h, self.footer,
                             report.fonts['subhead'])
            report.h += report.line_height
        report.c.restore()

    def draw_xlsx(self, report, worksheet):
        """Output program element to excel worksheet."""
        row = report.h
        if self.heading:
            worksheet.write(row, 2, self.heading.strip(), XLSX_STYLE['title'])
            row += 1
        if self.subheading:
            worksheet.write(row, 2, self.subheading.strip(),
                            XLSX_STYLE['subtitle'])
            row += 2
        else:
            row += 1
        if len(self.lines) > 0:
            rows = []
            if self.colheader:
                rows.append(vecmapstr(self.colheader, 7))
            for r in self.lines:
                nv = r[0:6]
                if len(nv) == 2:
                    nv = [nv[0], None, nv[1]]
                rows.append(vecmapstr(nv, 7))
                if len(r) > 6 and isinstance(r[6], (tuple, list)):
                    if r[6]:
                        nv = r[6]
                        rows.append(vecmapstr(nv, 7))
            if self.units:
                if self.colheader:
                    rows[1][6] = self.units
                else:
                    rows[0][6] = self.units
            for l in rows:
                worksheet.write(row, 0, l[0], XLSX_STYLE['left'])
                worksheet.write(row, 1, l[1], XLSX_STYLE['right'])
                worksheet.write(row, 2, l[2], XLSX_STYLE['left'])
                worksheet.write(row, 3, l[3], XLSX_STYLE['left'])
                worksheet.write(row, 4, l[4], XLSX_STYLE['right'])
                worksheet.write(row, 5, l[5], XLSX_STYLE['right'])
                worksheet.write(row, 6, l[6], XLSX_STYLE['left'])
                row += 1
            row += 1
        if self.footer:
            worksheet.write(row, 2, self.footer.strip(),
                            XLSX_STYLE['subtitle'])
            row += 2
        report.h = row
        return None

    def draw_text(self, report, f, xtn):
        """Write out a section in html."""
        if self.heading:
            f.write(htlib.h3(self.heading.strip(), {'id': self.sectionid}))
        if self.subheading:
            f.write(htlib.p(self.subheading.strip(), {'class': 'lead'}))

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
                if len(r) > 6 and isinstance(r[6], (tuple, list)):
                    if r[6]:
                        rows.append(r[6])
            if self.units:
                rows[0].append(self.units)
            trows = []
            for l in rows:
                trows.append(vec2htmlrow(l))
            f.write(
                htlib.table((hdr, htlib.tbody(trows)),
                            {'class': report.tablestyle}))
            f.write('\n')
        if self.footer:
            f.write(htlib.p(self.footer.strip()))
        return None


class section:

    def __init__(self, secid=''):
        self.sectionid = secid
        self.heading = None
        self.status = None
        self.subheading = None
        self.colheader = None
        self.units = None
        self.prizes = None
        self.footer = None
        self.lines = []
        self.lcount = 0
        self.grey = True
        self.nobreak = False
        self.h = None

    def serialize(self, rep, sectionid=None):
        """Return a serializable map for JSON export."""
        ret = {}
        if sectionid is None:
            sectionid = self.sectionid
        ret['sectionid'] = sectionid
        ret['type'] = 'section'
        ret['heading'] = self.heading
        ret['status'] = self.status
        ret['subheading'] = self.subheading
        ret['colheader'] = self.colheader
        ret['footer'] = self.footer
        ret['prizes'] = self.prizes
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
                if len(l) > 6 and l[6] and isinstance(l[6], (tuple, list)):
                    self.lcount += 1
            self.h = report.line_height * self.lcount
            if self.colheader:  # colheader is written out with body
                self.h += report.line_height
            if self.heading:
                self.h += report.section_height
            if self.subheading:
                self.h += report.section_height
            if self.footer:
                self.h += report.line_height
            if self.prizes:
                self.h += report.line_height
        return self.h

    def truncate(self, remainder, report):
        """Return a copy of the section up to page break."""

        # Special case: Entire section will fit on page
        if self.get_h(report) <= (remainder + report.page_overflow):
            return (self, None)

        # Special case: Don't break if possible
        if self.nobreak and report.pagefrac() > FEPSILON:
            # move entire section onto next page
            return (pagebreak(0.01), self)

        # Special case: Not enough space for minimum content
        chk = section()
        chk.heading = self.heading
        chk.subheading = self.subheading
        chk.colheader = self.colheader
        chk.footer = self.footer
        chk.prizes = self.prizes
        chk.units = self.units
        if len(self.lines) <= 4:  # special case, keep four or less together
            chk.lines = self.lines[0:]
        else:  # BUT, don't break before third rider
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
        ret.prizes = self.prizes
        ret.units = self.units
        rem.heading = self.heading
        rem.subheading = self.subheading
        rem.colheader = self.colheader
        rem.footer = self.footer
        rem.prizes = self.prizes
        rem.units = self.units
        if rem.heading is not None:
            if rem.heading.rfind('(continued)') < 0:
                rem.heading += ' (continued)'
        seclines = len(self.lines)
        count = 0
        if seclines > 0:
            while count < seclines and count < 3:  # don't break until 3rd
                ret.lines.append(self.lines[count])
                count += 1
        while count < seclines:
            if ret.get_h(report) > remainder:
                # pop last line onto rem and break
                rem.lines.append(ret.lines.pop(-1))
                break
            elif seclines - count <= 2:  # push min 2 names over to next page
                break
            ret.lines.append(self.lines[count])
            count += 1
        while count < seclines:
            rem.lines.append(self.lines[count])
            count += 1
        return (ret, rem)

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
            report.h += report.section_height
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
                        pass  #r[1] = u''
                    elif not (r[0] or r[1] or r[2] or r[3]):
                        cnt = 1  # empty row?
                    else:
                        cnt += 1
                else:
                    cnt = 1  # blank all 'empty' lines
                grey = 0
                if self.grey:
                    grey = (cnt + 1) % 2
                report.h += report.standard_row(report.h, r, grey)
                if len(r) > 6 and isinstance(r[6], (tuple, list)):
                    report.h += report.standard_row(report.h, r[6], grey)
            #eh = report.h	- for the column shade box
            #report.drawbox(report.col_oft_time-mm2pt(20.0), sh,
            #report.col_oft_time+mm2pt(1.0), eh, 0.07)
        if self.prizes:
            report.text_cent(report.midpagew, report.h, self.prizes,
                             report.fonts['subhead'])
            report.h += report.line_height
        if self.footer:
            report.text_cent(report.midpagew, report.h, self.footer,
                             report.fonts['subhead'])
            report.h += report.line_height
        report.c.restore()

    def draw_xlsx(self, report, worksheet):
        """Output program element to excel worksheet."""
        row = report.h
        if self.heading:
            worksheet.write(row, 2, self.heading.strip(), XLSX_STYLE['title'])
            row += 1
        if self.subheading:
            worksheet.write(row, 2, self.subheading.strip(),
                            XLSX_STYLE['subtitle'])
            row += 2
        else:
            row += 1
        if len(self.lines) > 0:
            rows = []
            cols = 7
            if self.colheader:
                cols = max(len(self.colheader), 7)
                rows.append(vecmapstr(self.colheader, 7))
            for r in self.lines:
                if cols == 7:
                    nv = r[0:6]
                    if len(nv) == 2:
                        nv = [nv[0], None, nv[1]]
                    rows.append(vecmapstr(nv, 7))
                    if len(r) > 6 and isinstance(r[6], (tuple, list)):
                        if r[6]:
                            nv = r[6]
                            rows.append(vecmapstr(nv, 7))
                else:
                    rows.append(vecmapstr(r, cols))
            if self.units:
                if self.colheader:
                    rows[1][6] = self.units
                else:
                    rows[0][6] = self.units
            for l in rows:
                worksheet.write(row, 0, l[0], XLSX_STYLE['left'])
                worksheet.write(row, 1, l[1], XLSX_STYLE['right'])
                worksheet.write(row, 2, l[2], XLSX_STYLE['left'])
                worksheet.write(row, 3, l[3], XLSX_STYLE['left'])
                worksheet.write(row, 4, l[4], XLSX_STYLE['right'])
                worksheet.write(row, 5, l[5], XLSX_STYLE['right'])
                worksheet.write(row, 6, l[6], XLSX_STYLE['left'])
                for k in range(7, cols):
                    worksheet.write(row, k, l[k], XLSX_STYLE['right'])
                row += 1
            row += 1
        if self.prizes:
            worksheet.write(row, 2, self.prizes.strip(),
                            XLSX_STYLE['subtitle'])
            row += 1
        if self.footer:
            worksheet.write(row, 2, self.footer.strip(),
                            XLSX_STYLE['subtitle'])
            row += 2
        report.h = row
        return None

    def draw_text(self, report, f, xtn):
        """Write out a section in html."""
        if self.heading:
            f.write(htlib.h3(self.heading.strip(), {'id': self.sectionid}))
        if self.subheading:
            f.write(htlib.p(self.subheading.strip(), {'class': 'lead'}))

        if len(self.lines) > 0:
            hdr = ''
            if self.colheader:
                hdr = htlib.thead(vec2htmlhead(self.colheader[0:6]))
            rows = []
            for r in self.lines:
                nv = list(r[0:6])
                if len(nv) == 2:
                    nv = [nv[0], None, nv[1]]
                rows.append(nv)
                if len(r) > 6 and isinstance(r[6], (tuple, list)):
                    if r[6]:
                        rows.append(r[6])
            if self.units:
                rows[0].append(self.units)
            trows = []
            for l in rows:
                trows.append(vec2htmlrow(l))
            f.write(
                htlib.table((hdr, htlib.tbody(trows)),
                            {'class': report.tablestyle}))
            f.write('\n')
        if self.prizes:
            f.write(htlib.p(self.prizes.strip(), {'class': 'text-italic'}))
        if self.footer:
            f.write(htlib.p(self.footer.strip()))
        return None


class pagebreak:
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
        except Exception as e:
            _log.warning('Invalid break thresh %r: %s', threshold, e)

    def get_threshold(self):
        return self.threshold


class image_elem:
    """Place an SVG image on the page."""

    def __init__(self,
                 x1=None,
                 y1=None,
                 x2=None,
                 y2=None,
                 halign=None,
                 valign=None,
                 source=None):
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
            if math.fabs(bh) < 0.0001:  # avoid div zero
                bh += 1.0  # but normally an error?
            ab = bw / bh
            iw = float(self.source.props.width)
            ih = float(self.source.props.height)
            ai = iw / ih
            xoft = 0.0
            yoft = 0.0
            sf = 1.0
            if ai > ab:  # 'wider' than box, scale to box w
                # xoft will be 0 for all aligns
                sf = bw / iw
                yoft = self.valign * (bh - ih * sf)
            else:  # 'higher' than box, scale to box h
                # yoft will be 0 for all aligns
                sf = bh / ih
                xoft = self.halign * (bw - iw * sf)
            self.sf = sf
            self.xof = self.x1 + xoft
            self.yof = self.y1 + yoft

    def draw(self, c, p):
        if self.source is not None:
            c.save()
            c.translate(self.xof, self.yof)
            c.scale(self.sf, self.sf)
            self.source.render_cairo(c)
            c.restore()


class arc_elem:
    """Pace an optionally shaded arc on the page."""

    def __init__(self,
                 cx=None,
                 cy=None,
                 r=None,
                 a1=None,
                 a2=None,
                 fill=None,
                 width=None,
                 colour=None,
                 dash=None):
        self.cx = cx
        self.cy = cy
        self.r = r
        self.a1 = a1
        self.a2 = a2
        self.fill = fill
        self.width = width
        self.colour = colour
        self.dash = dash

    def draw(self, c, p):
        c.save()
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
                c.set_source_rgb(self.colour[0], self.colour[1],
                                 self.colour[2])
            if self.dash is not None:
                c.set_dash(self.dash)
            c.stroke()
        c.restore()


class box_elem:
    """Place an optionally shaded box on the page."""

    def __init__(self,
                 x1=None,
                 y1=None,
                 x2=None,
                 y2=None,
                 fill=None,
                 width=None,
                 colour=None,
                 dash=None):
        self.x1 = x1
        self.y1 = y1
        self.x2 = x2
        self.y2 = y2
        self.fill = fill
        self.width = width
        self.colour = colour
        self.dash = dash

    def draw(self, c, p):
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
                c.set_source_rgb(self.colour[0], self.colour[1],
                                 self.colour[2])
            if self.dash is not None:
                c.set_dash(self.dash)
            c.stroke()
        c.restore()


class line_elem:
    """Places a line on the page."""

    def __init__(self,
                 x1=None,
                 y1=None,
                 x2=None,
                 y2=None,
                 width=None,
                 colour=None,
                 dash=None):
        self.x1 = x1
        self.y1 = y1
        self.x2 = x2
        self.y2 = y2
        self.width = width
        self.colour = colour
        self.dash = dash

    def draw(self, c, p):
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


class text_elem:
    """Places string of text on the page."""

    def __init__(self,
                 x=None,
                 y=None,
                 align=None,
                 font=None,
                 colour=None,
                 source=None,
                 report=None):
        self.x = x
        self.y = y
        self.align = align
        self.font = font
        self.colour = colour
        self.source = source
        self.report = report

    def draw(self, c, p):
        msg = None
        if self.source:
            if self.source in self.report.strings:
                if self.report.strings[self.source]:
                    msg = self.report.strings[self.source]
            else:
                msg = self.source
        if msg:
            c.save()
            l = Pango.Layout.new(p)
            if self.font is not None:
                l.set_font_description(self.font)
            if self.colour is not None:
                c.set_source_rgb(self.colour[0], self.colour[1],
                                 self.colour[2])
            l.set_text(msg, -1)
            (tw, th) = l.get_pixel_size()
            c.move_to(self.x - (self.align * tw), self.y)
            PangoCairo.update_context(c, p)
            l.context_changed()
            PangoCairo.show_layout(c, l)
            c.restore()


class group_elem:
    """Place each defined element on the page."""

    def __init__(self, report=None, elems=[]):
        self.report = report
        self.elems = elems
        self.indraw = False

    def draw(self, c, p):
        if self.indraw:
            return  # Ignore recursion
        self.indraw = True
        c.save()
        for e in self.elems:
            if e in self.report.elements:
                self.report.elements[e].draw(c, p)
        c.restore()
        self.indraw = False


class report:
    """PDF/GTKPrint Report class."""

    def __init__(self, template=None):

        # load template	-> also declares page geometry variables
        self.html_template = ''
        self.coverpage = None
        self.loadconfig(template)

        # override timestamp
        self.strings['timestamp'] = (
            str(date.today().strftime('%A, %B %d %Y ')) + tod.now().meridiem())
        self.strings[
            'watermark'] = 'Report: %s; Library: %s; Template: %s %r ' % (
                APIVERSION, metarace.VERSION, self.template_version,
                self.template_descr)
        if metarace.sysconf.has_value('report', 'watermark'):
            self.strings['watermark'] += metarace.sysconf.get(
                'report', 'watermark')

        # Status and context values
        self.provisional = False
        self.reportstatus = None  # optional flag for virtual etc
        self.serialno = str(int(time.time()))  # may be overidden
        self.eventid = None  # stage no or other identifier
        self.customlinks = []  # manual override links
        self.navbar = ''  # meet navigation
        self.showcard = True  # display meta card with HTML exports
        self.shortname = None
        self.prevlink = None
        self.nextlink = None
        self.indexlink = None
        self.resultlink = None
        self.startlink = None
        self.canonical = None
        self.pagemarks = False
        self.meetcode = None
        self.keywords = []
        self.s = None
        self.c = None
        self.p = None  # these are filled as required by the caller
        self.h = None  # position on page during write
        self.curpage = None  # current page in report
        self.sections = []  # source section data
        self.pages = []  # paginated sections

        # temporary col offset values...
        self.col_oft_rank = self.body_left  # left align
        self.col_oft_no = self.body_left + mm2pt(18)  # right align
        self.col_oft_name = self.body_left + mm2pt(19)  # left align
        self.col_oft_cat = self.body_right - mm2pt(62)  # ~left align
        self.col_oft_time = self.body_right - mm2pt(20)  # right align
        self.col_oft_xtra = self.body_right - mm2pt(2)  # right align
        self.col_oft_units = self.body_right - mm2pt(1)  # left

    def reset_geometry(self,
                       width=None,
                       height=None,
                       sidemargin=None,
                       endmargin=None,
                       topmargin=None,
                       botmargin=None,
                       printmargin=None):
        """Overwrite any new values and then compute page geometry."""
        if width is not None:
            self.pagew = width
        if height is not None:
            self.pageh = height
        if printmargin is not None:
            self.printmargin = printmargin
        if sidemargin is not None:
            self.sidemargin = sidemargin
        if endmargin is not None:
            self.endmargin = endmargin
        if topmargin is not None:
            self.topmargin = topmargin
        if botmargin is not None:
            self.botmargin = botmargin

        # compute midpage values
        self.midpagew = self.pagew / 2.0
        self.midpageh = self.pageh / 2.0

        # compute body region
        self.printh = self.pageh - self.printmargin - self.printmargin
        self.printw = self.pagew - self.printmargin - self.printmargin
        self.body_left = self.sidemargin
        self.body_right = self.pagew - self.sidemargin
        self.body_width = self.body_right - self.body_left
        self.col3_width = 0.90 * self.body_width / 3.0
        self.col1_right = self.body_left + self.col3_width
        self.col1t_left = self.body_left + mm2pt(1)
        self.col1t_right = self.col1_right - mm2pt(1)
        self.col2_left = self.midpagew - 0.5 * self.col3_width
        self.col2_right = self.col2_left + self.col3_width
        self.col2t_left = self.col2_left + mm2pt(1)
        self.col2t_right = self.col2_right - mm2pt(1)
        self.col3_left = self.body_right - self.col3_width
        self.col3t_left = self.col3_left + mm2pt(1)
        self.col3t_right = self.body_right - mm2pt(1)
        self.col3t_loft = [self.col1t_left, self.col2t_left, self.col3t_left]
        self.col3t_roft = [
            self.col1t_right, self.col2t_right, self.col3t_right
        ]
        self.body_top = self.topmargin
        self.body_bot = self.pageh - self.botmargin
        self.body_len = self.body_bot - self.body_top

    def loadconfig(self, template=None):
        """Initialise the report template."""

        # Default page geometry
        self.pagew = 595.0
        self.pageh = 842.0
        self.sidemargin = mm2pt(25.5)
        self.endmargin = mm2pt(36.2)
        self.topmargin = self.endmargin
        self.botmargin = self.endmargin
        self.printmargin = mm2pt(5.0)
        self.minbreak = 0.75  # minimum page break threshold

        # Default empty template elements
        self.colours = {}
        self.colours['white'] = [1.0, 1.0, 1.0]
        self.colours['shade'] = [0.9, 0.9, 0.9]
        self.colours['black'] = [0.0, 0.0, 0.0]
        self.elements = {}
        self.fonts = {}
        self.fonts['body'] = Pango.FontDescription(BODYFONT)
        self.fonts['bodysmall'] = Pango.FontDescription(BODYSMALL)
        self.fonts['bodyoblique'] = Pango.FontDescription(BODYFONT)
        self.fonts['bodybold'] = Pango.FontDescription(BODYBOLDFONT)
        self.fonts['section'] = Pango.FontDescription(SECTIONFONT)
        self.fonts['subhead'] = Pango.FontDescription(SUBHEADFONT)
        self.fonts['monospace'] = Pango.FontDescription(MONOSPACEFONT)
        self.fonts['provisional'] = Pango.FontDescription(PROVFONT)
        self.fonts['title'] = Pango.FontDescription(TITLEFONT)
        self.fonts['subtitle'] = Pango.FontDescription(SUBTITLEFONT)
        self.fonts['host'] = Pango.FontDescription(HOSTFONT)
        self.fonts['annotation'] = Pango.FontDescription(ANNOTFONT)
        self.gamutstdfont = GAMUTSTDFONT
        self.gamutobfont = GAMUTOBFONT
        self.tablestyle = TABLESTYLE
        self.buttonstyle = BUTTONSTYLE
        self.warnbuttonstyle = WARNBUTTONSTYLE
        self.strings = {}
        self.images = {}
        self.header = []
        self.template = None
        self.page_elem = None

        # read in from template
        cr = jsonconfig.config()
        cr.add_section('description')
        cr.add_section('page')
        cr.add_section('elements')
        cr.add_section('fonts')
        cr.add_section('strings')
        cr.add_section('colours')
        tfile = metarace.PDF_TEMPLATE
        if template is not None:
            tfile = template
        srcfile = metarace.default_file(tfile)
        if not cr.load(srcfile):
            try:
                _log.debug('Load report template from resource %s', tfile)
                cr.reads(metarace.resource_text(tfile))
            except Exception as e:
                _log.error('%s loading template: %s', e.__class__.__name__, e)
        self.template_version = ''
        self.template_descr = ''
        if cr.has_option('description', 'text'):
            _log.debug('API: %s, template: %s', APIVERSION,
                       cr.get('description', 'text'))
            self.template_descr = cr.get('description', 'text')
        else:
            _log.debug('API: %s, template: UNKNOWN', APIVERSION)
        if cr.has_option('description', 'version'):
            self.template_version = cr.get('description', 'version')
        if cr.has_option('description', 'keywords'):
            kw = cr.get('description', 'keywords')
            if isinstance(kw, list):
                self.keywords = []
                for k in kw:
                    if isinstance(k, str):
                        self.keywords.append(k)
        if cr.has_option('description', 'meetcode'):
            mc = cr.get('description', 'meetcode')
            if isinstance(mc, str):
                self.meetcode = mc

        # read in page options
        if cr.has_option('page', 'width'):
            self.pagew = str2len(cr.get('page', 'width'))
        if cr.has_option('page', 'height'):
            self.pageh = str2len(cr.get('page', 'height'))
        if cr.has_option('page', 'sidemargin'):
            self.sidemargin = str2len(cr.get('page', 'sidemargin'))
        if cr.has_option('page', 'endmargin'):
            self.endmargin = str2len(cr.get('page', 'endmargin'))
            self.topmargin = self.endmargin
            self.botmargin = self.endmargin
        if cr.has_option('page', 'topmargin'):
            self.topmargin = str2len(cr.get('page', 'topmargin'))
        if cr.has_option('page', 'botmargin'):
            self.botmargin = str2len(cr.get('page', 'botmargin'))
        if cr.has_option('page', 'printmargin'):
            self.printmargin = str2len(cr.get('page', 'printmargin'))
        if cr.has_option('page', 'minbreak'):
            self.minbreak = str2align(cr.get('page', 'minbreak'))
        self.section_height = SECTION_HEIGHT
        if cr.has_option('page', 'section_height'):
            self.section_height = str2len(cr.get('page', 'section_height'))
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
            cph = self.get_image(cr.get('page', 'coverpage'))
            if cph is not None:
                _log.debug('Adding coverpage to report')
                self.coverpage = image_elem(0.0, 0.0, self.pagew, self.pageh,
                                            0.5, 0.5, cph)
            else:
                _log.info('Coverpage file not found - skipped')

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
        # prepare the html wrapper and default styles
        if cr.has_option('page', 'html_template'):
            htfile = cr.get('page', 'html_template')
            if htfile:
                self.html_template = self.load_htmlfile(htfile)
                if '__REPORT_CONTENT__' not in self.html_template:
                    _log.debug('Invalid report HTML template ignored')
                    self.html_template = htlib.emptypage()
            else:
                self.html_template = htlib.emptypage()
        else:
            self.html_template = htlib.emptypage()
        if cr.has_option('page', 'tablestyle'):
            self.tablestyle = cr.get('page', 'tablestyle')
        if cr.has_option('page', 'buttonstyle'):
            self.buttonstyle = cr.get('page', 'buttonstyle')
        if cr.has_option('page', 'warnbuttonstyle'):
            self.warnbuttonstyle = cr.get('page', 'warnbuttonstyle')

    def load_htmlfile(self, templatefile):
        """Pull in a html template if it exists."""
        ret = ''
        fname = metarace.default_file(templatefile)
        if os.path.exists(fname):
            try:
                with open(fname, encoding='utf-8', errors='replace') as f:
                    ret = f.read()
            except Exception as e:
                _log.warning('%s reading HTML template %r: %s',
                             e.__class__.__name__, fname, e)
        else:
            _log.debug('HTML template %r not found', fname)
            ret = htlib.emptypage()
        return ret

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
                if os.path.exists(fname):
                    try:
                        rh = Rsvg.Handle()
                        fh = rh.new_from_file(fname)
                    except Exception as e:
                        _log.warning('%s loading SVG %r: %s',
                                     e.__class__.__name__, fname, e)
                self.images[key] = fh
            ret = self.images[key]
        return ret

    def pagepoint(self, pstr, orient='x'):
        """Convert a positional string into an absolute page reference."""
        ret = 0.0
        ref = self.pagew
        mid = self.midpagew
        if orient == 'y':  # vertical orientation
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
                ret = ref + relpos  # relative to bottom/right
            else:
                ret = relpos  # relative to top/left
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
            ret = line_elem(x1, y1, x2, y2, width, colour, dash)
        elif etype == 'image':
            x1 = self.pagepoint(emap[1], 'x')
            y1 = self.pagepoint(emap[2], 'y')
            x2 = self.pagepoint(emap[3], 'x')
            y2 = self.pagepoint(emap[4], 'y')
            halign = str2align(emap[5])
            valign = str2align(emap[6])
            source = self.get_image(emap[7])
            ret = image_elem(x1, y1, x2, y2, halign, valign, source)
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
            ret = box_elem(x1, y1, x2, y2, fill, width, colour, dash)
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
            ret = arc_elem(cx, cy, r, a1, a2, fill, width, colour, dash)
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
            ret = text_elem(x, y, align, font, colour, source, self)
        elif etype == 'group':  # slightly special case
            elist = estr.split(',')[1:]
            glist = []
            for e in elist:
                e = e.strip()
                if e:
                    glist.append(e)  # preserve ordering
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
            return  # breakout
        cur = 0
        while len(self.sections) > cur:
            if secid in self.sections[cur].sectionid:
                del (self.sections[cur])
            else:
                cur += 1

    def set_provisional(self, flag=True):
        self.provisional = flag

    def set_pagemarks(self, flag=True):
        self.pagemarks = flag

    def output_json(self, file=None):
        """Output the JSON version."""
        ret = self.serialise()
        # serialise to the provided file handle
        json.dump(ret, file, indent=1, sort_keys=True, cls=_publicEncoder)

    def serialise(self):
        """Return a serialisable report object"""
        if 'pagestr' in self.strings:
            del self.strings['pagestr']  # remove spurious string data
        ret = {
            'report': {},
            'sections': {},
            'api': 'metarace.report',
            'apiversion': APIVERSION,
            'libversion': metarace.VERSION
        }
        rep = ret['report']
        rep['provisional'] = self.provisional
        rep['reportstatus'] = self.reportstatus
        rep['eventid'] = self.eventid
        rep['serialno'] = self.serialno
        rep['prevlink'] = self.prevlink
        rep['nextlink'] = self.nextlink
        rep['indexlink'] = self.indexlink
        rep['resultlink'] = self.resultlink
        rep['startlink'] = self.startlink
        rep['canonical'] = self.canonical
        rep['customlinks'] = self.customlinks
        rep['shortname'] = self.shortname
        rep['pagemarks'] = self.pagemarks
        rep['strings'] = self.strings
        rep['meetcode'] = self.meetcode
        rep['keywords'] = self.keywords
        rep['sections'] = []
        secmap = ret['sections']
        for s in self.sections:
            secid = mksectionid(secmap, s.sectionid)
            secmap[secid] = s.serialize(self, secid)
            rep['sections'].append(secid)
        return ret

    def output_xlsx(self, file=None):
        """Output xlsx spreadsheet."""
        wb = xlsxwriter.Workbook(file, {'in_memory': True})

        sheetname = 'report'

        # Docstring?
        ws = wb.add_worksheet(sheetname)

        XLSX_STYLE['left'] = wb.add_format({'align': 'left'})
        XLSX_STYLE['right'] = wb.add_format({'align': 'right'})
        XLSX_STYLE['title'] = wb.add_format({'bold': True})
        XLSX_STYLE['subtitle'] = wb.add_format({'italic': True})
        XLSX_STYLE['monospace'] = wb.add_format({'font_name': 'Courier New'})
        XLSX_STYLE['laptime0'] = wb.add_format({
            'align': 'right',
            'num_format': '[m]:ss'
        })
        XLSX_STYLE['laptime1'] = wb.add_format({
            'align': 'right',
            'num_format': '[m]:ss.0'
        })
        XLSX_STYLE['laptime2'] = wb.add_format({
            'align': 'right',
            'num_format': '[m]:ss.00'
        })
        XLSX_STYLE['laptime3'] = wb.add_format({
            'align': 'right',
            'num_format': '[m]:ss.000'
        })

        # Set column widths using xlsxwriter format (width is in characters)
        ws.set_column(0, 0, 7)
        ws.set_column(1, 1, 5)
        ws.set_column(2, 2, 36)
        ws.set_column(3, 3, 12)
        ws.set_column(4, 4, 12)
        ws.set_column(5, 5, 12)

        title = ''
        for s in ['title', 'subtitle']:
            if s in self.strings and self.strings[s]:
                title += self.strings[s] + ' '
        ws.write(0, 2, title.strip(), XLSX_STYLE['title'])
        self.h = 2  # Start of 'document'
        for s in ['datestr', 'docstr', 'diststr', 'commstr', 'orgstr']:
            if s in self.strings and self.strings[s]:
                ws.write(self.h, 2, self.strings[s].strip(),
                         XLSX_STYLE['left'])
                self.h += 1
        self.h += 1
        if self.provisional:
            ws.write(self.h, 2, 'PROVISIONAL', XLSX_STYLE['title'])
            self.h += 2

        # output all the sections...
        for s in self.sections:
            if type(s) is not pagebreak:
                s.draw_xlsx(self, ws)  # call into section to draw

        wb.close()

    def macrowrite(self, file=None, text=''):
        """Write text to file substituting macros in text."""
        ttvec = []
        for s in ['title', 'subtitle']:
            if s in self.strings and self.strings[s]:
                ttvec.append(self.strings[s])
        titlestr = ' '.join(ttvec)
        ret = text
        if '__SERIALNO__' in ret:
            # workaround - until templates removed
            ret = ret.replace(
                '__SERIALNO__',
                'data-serialno=' + htlib.quoteattr(self.serialno))
        if '__REPORT_TITLE__' in ret:
            ret = ret.replace('__REPORT_TITLE__', htlib.escapetext(titlestr))
        if '__REPORT_NAV__' in ret:
            ret = ret.replace('__REPORT_NAV__', self.navbar)

        for s in self.strings:
            mackey = '__' + s.upper().strip() + '__'
            if mackey in ret:
                ret = ret.replace(mackey, htlib.escapetext(self.strings[s]))
        file.write(ret)

    def output_html(self, file=None, linkbase='', linktypes=[]):
        """Output a html version of the report."""
        cw = file
        navbar = []
        #for link in self.customlinks:  # to build custom toolbars
        #navbar.append(
        #htlib.a(link[0], {
        #'href': link[1] + '.html',
        #'class': 'nav-link'
        #}))
        if self.prevlink:
            navbar.append(
                htlib.a(
                    htlib.span((), {"class": "bi-caret-left"}), {
                        'href': self.prevlink + '.html',
                        'title': 'Previous',
                        'class': 'btn btn-secondary'
                    }))
        if self.indexlink:
            hrf = self.indexlink
            if hrf.startswith('.') or hrf.endswith('/') or hrf.endswith(
                    'html'):
                pass
            else:
                hrf += '.html'
            if hrf == 'index.html':
                hrf = './'

            navbar.append(
                htlib.a(htlib.span((), {"class": "bi-caret-up"}), {
                    'href': hrf,
                    'title': 'Index',
                    'class': 'btn btn-secondary'
                }))
        if self.startlink:
            navbar.append(
                htlib.a(
                    htlib.span((), {"class": "bi-file-earmark-person"}), {
                        'href': self.startlink + '.html',
                        'class': 'btn btn-secondary',
                        'title': 'Startlist'
                    }))
        if self.resultlink:
            navbar.append(
                htlib.a(
                    htlib.span((), {"class": "bi-file-earmark-text"}), {
                        'href': self.resultlink + '.html',
                        'class': 'btn btn-secondary',
                        'title': 'Result'
                    }))
        if self.provisional:  # add refresh button
            navbar.append(
                htlib.button(
                    htlib.span((), {"class": "bi-arrow-repeat"}), {
                        'id': 'pageReload',
                        'title': 'Reload',
                        "class": "btn btn-secondary"
                    }))
        if self.nextlink:
            navbar.append(
                htlib.a(
                    htlib.span((), {"class": "bi-caret-right"}), {
                        'href': self.nextlink + '.html',
                        'title': 'Next',
                        'class': 'btn btn-secondary'
                    }))
        brand = None
        if self.shortname:
            brand = htlib.a(self.shortname, {
                'href': './',
                'class': 'navbar-brand'
            })
        if len(navbar) > 0 or brand:  # write out bar if non-empty
            if not brand:
                brand = htlib.a('', {'href': '#', 'class': 'navbar-brand'})
            self.navbar = htlib.header(
                htlib.nav((brand, htlib.p(navbar, {'class': 'nav-item mb-0'})),
                          {'class': u'container'}),
                {
                    'class':
                    'navbar sticky-top navbar-expand-sm navbar-dark bg-dark mb-4'
                })

        (top, sep, bot) = self.html_template.partition('__REPORT_CONTENT__')

        # macro output the first part of the template
        self.macrowrite(cw, top)

        # output the body of the post
        self.output_htmlintext(cw, linkbase, linktypes, '.html')

        # macro output the footer of the template
        self.macrowrite(cw, bot)

    def output_htmlintext(self,
                          file=None,
                          linkbase='',
                          linktypes=[],
                          htmlxtn=''):
        """Output the html in text report body."""
        cw = file

        if self.showcard:
            ttvec = []
            for s in ['title', 'subtitle']:
                if s in self.strings and self.strings[s]:
                    ttvec.append(self.strings[s])
            titlestr = ' '.join(ttvec)

            if titlestr:
                cw.write(htlib.h2(titlestr.strip(), {'class': 'mb-4'}))
            if 'host' in self.strings and self.strings['host']:
                cw.write(htlib.p(self.strings['host'], {'class': 'lead'}))

            metalist = []
            for s in ['datestr', 'docstr', 'diststr', 'commstr', 'orgstr']:
                if s in self.strings and self.strings[s]:
                    metalist.append((ICONMAP[s], [self.strings[s].strip()]))
            if len(linktypes) > 0:
                linkmsg = ['Download as:']
                for xtn in linktypes:
                    xmsg = xtn
                    if xtn in FILETYPES:
                        xmsg = FILETYPES[xtn]
                    linkmsg.append(' [')
                    linkmsg.append(
                        htlib.a(xmsg, {'href': linkbase + '.' + xtn}))
                    linkmsg.append(']')
                metalist.append((ICONMAP['download'], linkmsg))
            if len(metalist) > 0:
                pmark = None
                if self.provisional:  # add prov marker
                    pmark = htlib.span('Provisional', {
                        'id': 'pgre',
                        'class': 'badge bg-warning'
                    })
                carditems = []
                for li in metalist:
                    items = [htlib.i('', {'class': li[0]})]
                    for c in li[1]:
                        items.append(c)
                    if pmark is not None:
                        items.append(pmark)
                    carditems.append(
                        htlib.li(items, {
                            'class':
                            'list-group-item list-group-item-secondary'
                        }))
                    pmark = None
                cw.write(
                    htlib.div(
                        htlib.ul(carditems,
                                 {'class': 'list-group list-group-flush'}),
                        {'class': 'card bg-light mb-4 small'}) + '\n')

        # output all the sections...
        secmap = {}
        for s in self.sections:
            secid = mksectionid(secmap, s.sectionid)
            secmap[secid] = secid
            s.sectionid = secid
        for s in self.sections:
            if type(s) is not pagebreak:
                s.draw_text(self, cw, htmlxtn)  # call into section

        cw.write('\n')

    def set_context(self, context):
        self.s = None
        self.c = context
        self.p = PangoCairo.create_context(self.c)

    def start_gtkprint(self, context):
        """Prepare document for a gtkPrint output."""
        self.s = None
        self.c = context
        self.p = PangoCairo.create_context(self.c)

        # break report into pages as required
        self.paginate()

        # Special case: remove an empty final page
        if len(self.pages) > 0 and len(self.pages[-1]) == 0:
            del self.pages[-1]

    def output_pdf(self, file=None, docover=False):
        """Prepare document and then output to a PDF surface."""

        # create output cairo surface and save contexts
        self.s = cairo.PDFSurface(file, self.pagew, self.pageh)
        self.c = cairo.Context(self.s)
        self.p = PangoCairo.create_context(self.c)

        # break report into pages as required
        self.paginate()

        # Special case: remove an empty final page
        if len(self.pages) > 0 and len(self.pages[-1]) == 0:
            del self.pages[-1]
        npages = self.get_pages()

        # if coverpage present, output
        if docover and self.coverpage is not None:
            self.draw_cover()
            self.c.show_page()  # start a new blank page

        # output each page
        for i in range(0, npages):
            self.draw_page(i)
            if i < npages - 1:
                self.c.show_page()  # start a new blank page

        # finalise surface - may be a blank pdf if no content
        self.s.flush()
        self.s.finish()

    def draw_element(self, elem):
        """Draw the named element if it is defined."""
        if elem in self.elements:
            self.elements[elem].draw(self.c, self.p)
        else:
            pass

    def draw_template(self):
        """Draw page layout."""
        for e in self.header:
            self.draw_element(e)
        self.draw_element('pagestr')

    def draw_cover(self):
        """Draw a coverpage."""
        # clip page print extents
        self.c.save()
        self.c.rectangle(self.printmargin, self.printmargin, self.printw,
                         self.printh)
        self.c.clip()
        # draw page template
        if self.provisional:
            self.draw_provisional()

        # place cover image
        self.coverpage.draw(self.c, self.p)

        # if requested, overlay page marks
        if self.pagemarks:
            self.draw_pagemarks()

        # restore context
        self.c.restore()

    def draw_page(self, page_nr):
        """Draw the current page onto current context."""

        # clip page print extents
        self.c.save()
        self.c.rectangle(self.printmargin, self.printmargin, self.printw,
                         self.printh)
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
                s.draw_pdf(self)  # call into section to draw
                self.h += self.line_height  # inter-section gap

        # if requested, overlay page marks
        if self.pagemarks:
            self.draw_pagemarks()

        # restore context
        self.c.restore()

    def teamname_height(self, text, width=None):
        """Determine height of a team name wrapped at width."""
        ret = 0
        if width is None:
            width = self.body_width
        l = Pango.Layout.new(self.p)
        if self.fonts['section'] is not None:
            l.set_font_description(self.fonts['section'])
        l.set_width(int(Pango.SCALE * width + 1))
        l.set_wrap(Pango.WrapMode.WORD)
        l.set_alignment(Pango.Alignment.LEFT)
        l.set_text(text, -1)
        (tw, th) = l.get_pixel_size()
        ret = th
        return ret

    def paragraph_height(self, text, width=None):
        """Determine height of a paragraph at the desired width."""
        ret = 0
        if width is None:
            width = self.body_width
        l = Pango.Layout.new(self.p)
        if self.fonts['body'] is not None:
            l.set_font_description(self.fonts['body'])
        l.set_width(int(Pango.SCALE * width + 1))
        l.set_wrap(Pango.WrapMode.WORD_CHAR)
        l.set_alignment(Pango.Alignment.LEFT)
        l.set_text(text, -1)
        (tw, th) = l.get_pixel_size()
        ret = th
        return ret

    def preformat_height(self, rows):
        """Determine height of a block of preformatted text."""
        ret = 0
        if len(rows) > 0:
            ostr = 'M' + 'L\n' * (len(rows) - 1) + 'LM'
            l = Pango.Layout.new(self.p)
            if self.fonts['monospace'] is not None:
                l.set_font_description(self.fonts['monospace'])
            l.set_text(ostr, -1)
            (tw, th) = l.get_pixel_size()
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
            l = Pango.Layout.new(self.p)
            if self.fonts['body'] is not None:
                l.set_font_description(self.fonts['body'])
            l.set_text('\n'.join(rvec), -1)
            (tw, th) = l.get_pixel_size()
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
                    nval = str(r[1])
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
                (junk, ret) = self.text_left(oft, self.h, '\n'.join(rvec),
                                             self.fonts['body'])
            else:
                (junk, ret) = self.text_right(oft, self.h, '\n'.join(rvec),
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
        return (self.h - self.body_top) / self.body_len

    def paginate(self):
        """Scan report content and paginate sections."""

        # initialise
        self.pages = []
        curpage = self.newpage()

        for r in self.sections:
            s = r
            while s is not None:
                if type(s) is pagebreak:
                    bpoint = s.get_threshold()
                    if bpoint is None:
                        bpoint = self.minbreak
                    if self.pagefrac() > bpoint:
                        curpage = self.newpage()  # conditional break
                    s = None
                else:
                    (o, s) = s.truncate(self.pagerem(), self)
                    if type(o) is pagebreak:
                        curpage = self.newpage()  # mandatory break
                    else:
                        curpage.append(o)
                        self.h += o.get_h(self)
                        if s is not None:  # section broken to new page
                            curpage = self.newpage()
                        else:
                            self.h += self.line_height  # inter sec gap

    def draw_pagemarks(self):
        """Draw page layout markings on current page."""
        dash = [mm2pt(1)]
        self.c.save()  # start group
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
        self.c.move_to(self.pagew, self.pageh - self.midpagew)
        self.c.arc(self.midpagew, self.pageh - self.midpagew, self.midpagew,
                   0.0, math.pi)
        self.c.stroke()

        # Body cropping from page geometry
        self.c.set_source_rgb(0.0, 1.0, 0.0)
        self.c.move_to(0, self.body_top)
        self.c.line_to(self.pagew, self.body_top)
        self.c.move_to(self.body_left, 0)
        self.c.line_to(self.body_left, self.pageh)
        self.c.move_to(0, self.body_bot)
        self.c.line_to(self.pagew, self.body_bot)
        self.c.move_to(self.body_right, 0)
        self.c.line_to(self.body_right, self.pageh)
        self.c.stroke()

        self.c.restore()  # end group

    def get_baseline(self, h):
        """Return the baseline for a given height."""
        return h + 0.9 * self.line_height  # check baseline at other sz

    def laplines(self, h, laps, start, finish, endh=None, reverse=False):
        sp = self.col_oft_cat - mm2pt(20.0)
        fac = mm2pt(40.0) / float((finish - start).timeval)
        top = h + 0.15 * self.line_height
        bot = h + 0.85 * self.line_height
        if reverse:
            self.c.save()
            self.c.set_source_rgba(0.5, 0.5, 0.5, 0.3)
        if endh is not None:
            bot = endh - 0.15 * self.line_height
        for l in laps:
            lt = tod.mktod(l)
            if lt is not None:
                if lt > start and (finish is None or lt < finish):
                    toft = sp + float((lt - start).timeval) * fac
                    self.drawline(toft, top, toft, bot)
        if reverse:
            self.c.restore()

    def judges_row(self, h, rvec, zebra=None, strikethrough=False):
        """Output a standard section row, and return the row height."""
        if zebra:
            self.drawbox(self.body_left - mm2pt(1), h,
                         self.body_right + mm2pt(1), h + self.line_height,
                         0.07)
        omap = vecmap(rvec, 9)
        strikeright = self.col_oft_rank
        if omap[0]:
            if omap[8]:  # Photo-finish
                font = self.fonts['bodysmall']
                self.text_left(self.col_oft_rank, h, '\U0001f4f7', font)
            elif omap[0] == '____':
                font = self.fonts['body']
                self.text_left(self.col_oft_rank,
                               h,
                               '\u3000' * 2,
                               font,
                               underline=True)
            else:
                font = self.fonts['body']
                if not omap[7]:  # Placed
                    font = self.fonts['bodyoblique']
                self.text_left(self.col_oft_rank, h, omap[0], font)
        if omap[1]:
            self.text_right(self.col_oft_no, h, omap[1], self.fonts['body'])
            strikeright = self.col_oft_rank
        if omap[2]:
            maxnamew = (self.col_oft_cat - mm2pt(35.0)) - self.col_oft_name
            (tw, th) = self.fit_text(self.col_oft_name,
                                     h,
                                     omap[2],
                                     maxnamew,
                                     font=self.fonts['body'])
            strikeright = self.col_oft_name + tw
        if len(rvec) > 10 and rvec[10]:
            catw = mm2pt(8.0)
            (tw, th) = self.fit_text(self.col_oft_cat - mm2pt(34.0),
                                     h,
                                     rvec[10],
                                     catw,
                                     font=self.fonts['body'])
            strikeright = self.col_oft_cat
        if omap[3]:
            (tw, th) = self.text_left(self.col_oft_cat - mm2pt(25.0), h,
                                      omap[3], self.fonts['body'])
            strikeright = self.col_oft_cat + tw
        if omap[4]:
            self.text_right(self.col_oft_time, h, omap[4], self.fonts['body'])
            strikeright = self.col_oft_time
        if omap[5]:
            self.text_right(self.col_oft_xtra, h, omap[5], self.fonts['body'])
            strikeright = self.col_oft_xtra
        if strikethrough:
            self.drawline(self.body_left + mm2pt(1),
                          h + (0.5 * self.line_height), strikeright,
                          h + (0.5 * self.line_height))
        return self.line_height

    def gamut_cell(self,
                   h,
                   x,
                   height,
                   width,
                   key,
                   alpha=0.05,
                   fonts={},
                   data=None):
        """Draw a gamut cell and add data if available."""
        self.drawbox(x, h, x + width - mm2pt(0.5), h + height - mm2pt(0.5),
                     alpha)
        if key:
            self.gtext_left(x + mm2pt(0.5), h + 0.15 * height, key,
                            fonts['key'])
        if data is not None:
            if data['name']:
                self.gfit_text(x + width - mm2pt(1.0),
                               h + (0.05 * height),
                               data['name'],
                               width - mm2pt(1.5),
                               right=True,
                               font=fonts['text'])
            if data['gcline']:
                self.gtext_right(x + width - mm2pt(1.0), h + (0.30 * height),
                                 data['gcline'], fonts['gcline'])
            if data['ltext']:
                self.gtext_left(x + mm2pt(0.5), h + (0.66 * height),
                                data['ltext'], fonts['text'])
            if data['rtext']:
                self.gtext_right(x + width - mm2pt(1.0), h + (0.66 * height),
                                 data['rtext'], fonts['text'])
            if data['dnf']:
                self.drawline(x + mm2pt(0.5),
                              h + height - mm2pt(1.0),
                              x + width - mm2pt(1.0),
                              h + mm2pt(0.5),
                              width=1.5)
        return height

    def standard_3row(self, h, rv1, rv2, rv3, zebra=None, strikethrough=False):
        """Output a standard 3 col section row, and return the row height."""
        if zebra:
            self.drawbox(self.body_left - mm2pt(1), h,
                         self.col1_right + mm2pt(1), h + self.line_height,
                         0.07)
            self.drawbox(self.col2_left - mm2pt(1), h,
                         self.col2_right + mm2pt(1), h + self.line_height,
                         0.07)
            self.drawbox(self.col3_left - mm2pt(1), h,
                         self.body_right + mm2pt(1), h + self.line_height,
                         0.07)
        omap1 = vecmap(rv1, 7)
        omap2 = vecmap(rv2, 7)
        omap3 = vecmap(rv3, 7)

        # 3 column references
        if omap1[2]:
            self.text_left(self.col1t_left, h, omap1[2], self.fonts['body'])
        if omap1[4]:
            self.text_right(self.col1t_left + 0.60 * self.col3_width, h,
                            omap1[4], self.fonts['body'])
        if omap1[5]:
            self.text_right(self.col1t_right, h, omap1[5], self.fonts['body'])
        if strikethrough:
            self.drawline(self.col1t_left + mm2pt(1),
                          h + (0.5 * self.line_height),
                          self.col1t_right - mm2pt(1),
                          h + (0.5 * self.line_height))
        if omap2[2]:
            self.text_left(self.col2t_left, h, omap2[2], self.fonts['body'])
        if omap2[4]:
            self.text_right(self.col2t_left + 0.60 * self.col3_width, h,
                            omap2[4], self.fonts['body'])
        if omap2[5]:
            self.text_right(self.col2t_right, h, omap2[5], self.fonts['body'])
        if strikethrough:
            self.drawline(self.col2t_left + mm2pt(1),
                          h + (0.5 * self.line_height),
                          self.col2t_right - mm2pt(1),
                          h + (0.5 * self.line_height))
        if omap3[2]:
            self.text_left(self.col3t_left, h, omap3[2], self.fonts['body'])
        if omap3[4]:
            self.text_right(self.col3t_left + 0.60 * self.col3_width, h,
                            omap3[4], self.fonts['body'])
        if omap3[5]:
            self.text_right(self.col3t_right, h, omap3[5], self.fonts['body'])
        if strikethrough:
            self.drawline(self.col3t_left + mm2pt(1),
                          h + (0.5 * self.line_height),
                          self.col3t_right - mm2pt(1),
                          h + (0.5 * self.line_height))

        return self.line_height

    def standard_row(self, h, rvec, zebra=None, strikethrough=False):
        """Output a standard section row, and return the row height."""
        if zebra:
            self.drawbox(self.body_left - mm2pt(1), h,
                         self.body_right + mm2pt(1), h + self.line_height,
                         0.07)
        omap = vecmap(rvec, 7)
        strikeright = self.col_oft_rank
        if omap[0]:
            self.text_left(self.col_oft_rank, h, omap[0], self.fonts['body'])
        if omap[1]:
            self.text_right(self.col_oft_no, h, omap[1], self.fonts['body'])
            strikeright = self.col_oft_rank
        if omap[2]:
            maxnamew = self.col_oft_cat - self.col_oft_name
            if not omap[3]:
                maxnamew = self.col_oft_time - self.col_oft_name - mm2pt(20)
            (tw, th) = self.fit_text(self.col_oft_name,
                                     h,
                                     omap[2],
                                     maxnamew,
                                     font=self.fonts['body'])
            strikeright = self.col_oft_name + tw
        if omap[3]:
            (tw, th) = self.text_left(self.col_oft_cat, h, omap[3],
                                      self.fonts['body'])
            strikeright = self.col_oft_cat + tw
        if omap[4]:
            self.text_right(self.col_oft_time, h, omap[4], self.fonts['body'])
            strikeright = self.col_oft_time
        if omap[5]:
            self.text_right(self.col_oft_xtra, h, omap[5], self.fonts['body'])
            strikeright = self.col_oft_xtra
        if strikethrough:
            self.drawline(self.body_left + mm2pt(1),
                          h + (0.5 * self.line_height), strikeright,
                          h + (0.5 * self.line_height))
        return self.line_height

    def rttstart_row(self, h, rvec, zebra=None, strikethrough=False):
        """Output a time trial start row, and return the row height."""
        if zebra:
            self.drawbox(self.body_left - mm2pt(1), h,
                         self.body_right + mm2pt(1), h + self.line_height,
                         0.07)
        omap = vecmap(rvec, 7)
        strikeright = self.col_oft_name + mm2pt(16)
        if omap[0]:
            self.text_right(self.col_oft_name + mm2pt(1), h, omap[0],
                            self.fonts['body'])
        if omap[4]:
            self.text_left(self.col_oft_name + mm2pt(2), h, omap[4],
                           self.fonts['body'])
        if omap[1]:
            self.text_right(self.col_oft_name + mm2pt(16), h, omap[1],
                            self.fonts['body'])
        if omap[2]:
            maxnamew = self.col_oft_cat - self.col_oft_name  # both oft by 20
            if not omap[3]:
                maxnamew = self.col_oft_xtra - self.col_oft_name
            (tw, th) = self.fit_text(self.col_oft_name + mm2pt(20),
                                     h,
                                     omap[2],
                                     maxnamew,
                                     font=self.fonts['body'])
            #(tw,th) = self.text_left(self.col_oft_name+mm2pt(20), h,
            #omap[2], self.fonts[u'body'])
            strikeright = self.col_oft_name + mm2pt(20) + tw
        if omap[3]:
            (tw, th) = self.text_left(self.col_oft_cat + mm2pt(20), h, omap[3],
                                      self.fonts['body'])
            strikeright = self.col_oft_cat + mm2pt(20) + tw
        if omap[5]:
            self.text_right(self.col_oft_xtra, h, omap[5], self.fonts['body'])
            strikeright = self.body_right - mm2pt(1)
        if strikethrough:
            self.drawline(self.body_left + mm2pt(1),
                          h + (0.5 * self.line_height), strikeright,
                          h + (0.5 * self.line_height))
        return self.line_height

    def ittt_lane(self, rvec, w, h, drawline=True, truncate=False):
        """Draw a single lane."""
        baseline = self.get_baseline(h)
        if rvec[0] is None:  # rider no None implies no rider
            self.text_left(w + mm2pt(8), h, '[No Rider]', self.fonts['body'])
        else:
            if rvec[0]:  # non-empty rider no implies full info
                self.text_right(w + mm2pt(7), h, rvec[0], self.fonts['body'])
                if truncate:
                    self.fit_text(w=w + mm2pt(8.0),
                                  h=h,
                                  msg=rvec[1],
                                  font=self.fonts['body'],
                                  maxwidth=mm2pt(50.0))
                else:
                    self.text_left(w + mm2pt(8), h, rvec[1],
                                   self.fonts['body'])
            else:  # otherwise draw placeholder lines
                self.drawline(w, baseline, w + mm2pt(7), baseline)
                self.drawline(w + mm2pt(8), baseline, w + mm2pt(58), baseline)
            if drawline:
                self.drawline(w + mm2pt(59), baseline, w + mm2pt(75), baseline)

    def ittt_heat(self, hvec, h, dual=False, showheat=True):
        """Output a single time trial heat."""
        if showheat:
            # allow for a heat holder but no text...
            if hvec[0] and hvec[0] != '-':
                self.text_left(self.body_left, h, 'Heat ' + str(hvec[0]),
                               self.fonts['subhead'])
            h += self.line_height
        rcnt = 1  # assume one row unless team members
        tcnt = 0
        if len(hvec) > 3:  # got a front straight
            self.ittt_lane([hvec[1], hvec[2]],
                           self.body_left,
                           h,
                           truncate=True)
            if isinstance(hvec[3], (tuple, list)):  # additional 'team' rows
                tcnt = len(hvec[3])
                tof = h + self.line_height
                for t in hvec[3]:
                    self.ittt_lane([t[0], t[1]],
                                   self.body_left,
                                   tof,
                                   drawline=False)
                    tof += self.line_height
        if len(hvec) > 7:  # got a back straight
            if hvec[5] is not None:
                self.text_cent(self.midpagew, h, 'v', self.fonts['subhead'])
            self.ittt_lane([hvec[5], hvec[6]],
                           self.midpagew + mm2pt(5),
                           h,
                           truncate=True)
            if isinstance(hvec[7], (tuple, list)):  # additional 'team' rows
                tcnt = max(tcnt, len(hvec[7]))
                tof = h + self.line_height
                for t in hvec[7]:
                    self.ittt_lane([t[0], t[1]],
                                   self.midpagew + mm2pt(5),
                                   tof,
                                   drawline=False)
                    tof += self.line_height
        elif dual:
            # No rider, but other heats are dual so add marker
            self.ittt_lane([None, None], self.midpagew + mm2pt(5), h)
        h += (rcnt + tcnt) * self.line_height

        return h

    def sprint_rider(self, rvec, w, h):
        baseline = self.get_baseline(h)
        # ignore rank in sprint round - defer to other markup
        doline = True
        if rvec[1]:  # rider no
            self.text_right(w + mm2pt(5.0), h, rvec[1], self.fonts['body'])
            doline = False
        if rvec[2]:  # rider name
            self.fit_text(w=w + mm2pt(6.0),
                          h=h,
                          msg=rvec[2],
                          font=self.fonts['body'],
                          maxwidth=mm2pt(39.0))
            doline = False
        if rvec[3]:  # qualifying time
            self.text_left(w + mm2pt(45.0), h, 'Q: ' + rvec[3],
                           self.fonts['bodyoblique'])
        if doline:
            self.drawline(w + mm2pt(1.0), baseline, w + mm2pt(50), baseline)
        # ignore cat/xtra in sprint rounds

    def sign_box(self, rvec, w, h, lineheight, zebra):
        baseline = h + lineheight + lineheight
        if zebra:
            self.drawbox(w, h, w + self.twocol_width, baseline, 0.07)
        self.drawline(w, baseline, w + self.twocol_width, baseline)
        if len(rvec) > 1 and rvec[1]:  # rider no
            self.text_right(w + mm2pt(7.0), h, rvec[1], self.fonts['body'])
        if len(rvec) > 2 and rvec[2]:  # rider name
            self.fit_text(w + mm2pt(9.0),
                          h,
                          rvec[2],
                          self.twocol_width - mm2pt(9.0),
                          font=self.fonts['body'])
            if rvec[0] == 'dns':
                mgn = mm2pt(1.5)
                self.drawline(w + mgn, h + mgn, w + self.twocol_width - mgn,
                              baseline - mgn)

    def rms_rider(self, rvec, w, h):
        baseline = self.get_baseline(h)
        if len(rvec) > 0 and rvec[0] is not None:
            self.text_left(w, h, rvec[0], self.fonts['body'])
        else:
            self.drawline(w, baseline, w + mm2pt(4), baseline)
        doline = True
        if len(rvec) > 1 and rvec[1]:  # rider no
            self.text_right(w + mm2pt(8.0), h, rvec[1], self.fonts['body'])
            doline = False
        if len(rvec) > 2 and rvec[2]:  # rider name
            #self.text_left(w+mm2pt(11.0), h, rvec[2], self.fonts[u'body'])
            self.fit_text(w + mm2pt(9.0),
                          h,
                          rvec[2],
                          mm2pt(50),
                          font=self.fonts['body'])
            doline = False
        if doline:
            self.drawline(w + mm2pt(8.0), baseline, w + mm2pt(60), baseline)
        if len(rvec) > 3 and rvec[3]:  # cat/hcap/draw/etc
            self.text_left(w + mm2pt(59.0), h, rvec[3],
                           self.fonts['bodyoblique'])

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

    def fit_text(self,
                 w,
                 h,
                 msg,
                 maxwidth,
                 right=False,
                 font=None,
                 strikethrough=False,
                 underline=False):
        tw = 0
        th = self.line_height
        if msg:
            baseline = _CELL_BASELINE * self.line_height
            l = Pango.Layout.new(self.p)
            if right:
                l.set_alignment(Pango.Alignment.RIGHT)
                l.set_ellipsize(Pango.EllipsizeMode.START)
            else:
                l.set_alignment(Pango.Alignment.LEFT)
                l.set_ellipsize(Pango.EllipsizeMode.END)
            if font is not None:
                l.set_font_description(font)

            l.set_wrap(Pango.WrapMode.WORD_CHAR)
            l.set_text(msg, -1)
            l.set_width(int(maxwidth * PANGO_SCALE))
            l.set_height(0)
            intr, logr = l.get_extents()
            fnbaseline = l.get_baseline() * PANGO_INVSCALE
            thof = logr.y * PANGO_INVSCALE
            twof = logr.x * PANGO_INVSCALE
            tw = logr.width * PANGO_INVSCALE
            th = logr.height * PANGO_INVSCALE
            oft = w + twof
            if right:
                oft = w - (tw + twof)
            self.c.move_to(oft, h + (baseline - fnbaseline) + thof)
            PangoCairo.update_context(self.c, self.p)
            l.context_changed()
            PangoCairo.show_layout(self.c, l)

            metrics = None
            if strikethrough or underline:
                metrics = l.get_context().get_metrics(font)
            if strikethrough:
                strikethick = metrics.get_strikethrough_thickness(
                ) * PANGO_INVSCALE
                strikeoft = baseline - metrics.get_strikethrough_position(
                ) * PANGO_INVSCALE
                sth = h + strikeoft - 0.5 * strikethick
                self.drawline(oft, sth, oft + tw, sth, strikethick)
            if underline:
                underthick = metrics.get_underline_thickness() * PANGO_INVSCALE
                underoft = baseline - metrics.get_underline_position(
                ) * PANGO_INVSCALE
                uth = h + underoft - 0.5 * underthick
                self.drawline(oft, uth, oft + tw, uth, underthick)
        return (tw, th)

    def gfit_text(self,
                  w,
                  h,
                  msg,
                  maxwidth,
                  right=False,
                  font=None,
                  strikethrough=False,
                  underline=False):
        tw = 0
        th = self.line_height
        if msg:
            baseline = _CELL_BASELINE * self.line_height
            l = Pango.Layout.new(self.p)
            if right:
                l.set_alignment(Pango.Alignment.RIGHT)
                l.set_ellipsize(Pango.EllipsizeMode.START)
            else:
                l.set_alignment(Pango.Alignment.LEFT)
                l.set_ellipsize(Pango.EllipsizeMode.END)
            if font is not None:
                l.set_font_description(font)

            l.set_wrap(Pango.WrapMode.WORD_CHAR)
            l.set_text(msg, -1)
            l.set_width(int(maxwidth * PANGO_SCALE))
            l.set_height(0)
            intr, logr = l.get_extents()
            fnbaseline = l.get_baseline() * PANGO_INVSCALE
            thof = logr.y * PANGO_INVSCALE
            twof = logr.x * PANGO_INVSCALE
            tw = logr.width * PANGO_INVSCALE
            th = logr.height * PANGO_INVSCALE
            oft = w + twof
            if right:
                oft = w - (tw + twof)
            self.c.move_to(oft, h)
            #self.c.move_to(oft, h + (baseline - fnbaseline) + thof)
            PangoCairo.update_context(self.c, self.p)
            l.context_changed()
            PangoCairo.show_layout(self.c, l)

            metrics = None
            if strikethrough or underline:
                metrics = l.get_context().get_metrics(font)
            if strikethrough:
                strikethick = metrics.get_strikethrough_thickness(
                ) * PANGO_INVSCALE
                strikeoft = baseline - metrics.get_strikethrough_position(
                ) * PANGO_INVSCALE
                sth = h + strikeoft - 0.5 * strikethick
                self.drawline(oft, sth, oft + tw, sth, strikethick)
            if underline:
                underthick = metrics.get_underline_thickness() * PANGO_INVSCALE
                underoft = baseline - metrics.get_underline_position(
                ) * PANGO_INVSCALE
                uth = h + underoft - 0.5 * underthick
                self.drawline(oft, uth, oft + tw, uth, underthick)
        return (tw, th)

    def placemark(self, w, h):
        """Draw a crosshair mark at w,h"""
        self.drawline(w, h - 2.5, w, h + 2.5, 0.10)
        self.drawline(w - 2.5, h, w + 2.5, h, 0.10)
        self.c.save()
        self.c.set_line_width(0.10)
        self.c.new_sub_path()
        self.c.arc(w, h, 1.0, 0.0, 2.0 * math.pi)
        self.c.stroke()
        self.c.restore()

    def text_right(self,
                   w,
                   h,
                   msg,
                   font=None,
                   strikethrough=False,
                   maxwidth=None,
                   underline=False):
        # TODO: replace with text_cell
        tw = 0
        th = self.line_height
        if msg:
            baseline = _CELL_BASELINE * self.line_height

            l = Pango.Layout.new(self.p)
            l.set_alignment(Pango.Alignment.RIGHT)
            if font is not None:
                l.set_font_description(font)
            l.set_text(msg, -1)
            intr, logr = l.get_extents()
            fnbaseline = l.get_baseline() * PANGO_INVSCALE
            thof = logr.y * PANGO_INVSCALE
            twof = logr.x * PANGO_INVSCALE
            tw = logr.width * PANGO_INVSCALE
            th = logr.height * PANGO_INVSCALE
            oft = w - (tw + twof)
            self.c.move_to(oft, h + (baseline - fnbaseline) + thof)
            PangoCairo.update_context(self.c, self.p)
            l.context_changed()
            PangoCairo.show_layout(self.c, l)

            metrics = None
            if underline or strikethrough:
                metrics = l.get_context().get_metrics(font)
            if strikethrough:
                strikethick = metrics.get_strikethrough_thickness(
                ) * PANGO_INVSCALE
                strikeoft = baseline - metrics.get_strikethrough_position(
                ) * PANGO_INVSCALE
                sth = h + strikeoft - 0.5 * strikethick
                self.drawline(oft, sth, oft + tw, sth, strikethick)
            if underline:
                underthick = metrics.get_underline_thickness() * PANGO_INVSCALE
                underoft = baseline - metrics.get_underline_position(
                ) * PANGO_INVSCALE
                uth = h + underoft - 0.5 * underthick
                self.drawline(oft, uth, oft + tw, uth, underthick)
        return (tw, th)

    def gtext_right(self,
                    w,
                    h,
                    msg,
                    font=None,
                    strikethrough=False,
                    maxwidth=None,
                    underline=False):
        # TODO: replace with text_cell
        tw = 0
        th = self.line_height
        if msg:
            baseline = _CELL_BASELINE * self.line_height

            l = Pango.Layout.new(self.p)
            l.set_alignment(Pango.Alignment.RIGHT)
            if font is not None:
                l.set_font_description(font)
            l.set_text(msg, -1)
            intr, logr = l.get_extents()
            fnbaseline = l.get_baseline() * PANGO_INVSCALE
            thof = logr.y * PANGO_INVSCALE
            twof = logr.x * PANGO_INVSCALE
            tw = logr.width * PANGO_INVSCALE
            th = logr.height * PANGO_INVSCALE
            oft = w - (tw + twof)
            self.c.move_to(oft, h)
            PangoCairo.update_context(self.c, self.p)
            l.context_changed()
            PangoCairo.show_layout(self.c, l)

            metrics = None
            if underline or strikethrough:
                metrics = l.get_context().get_metrics(font)
            if strikethrough:
                strikethick = metrics.get_strikethrough_thickness(
                ) * PANGO_INVSCALE
                strikeoft = baseline - metrics.get_strikethrough_position(
                ) * PANGO_INVSCALE
                sth = h + strikeoft - 0.5 * strikethick
                self.drawline(oft, sth, oft + tw, sth, strikethick)
            if underline:
                underthick = metrics.get_underline_thickness() * PANGO_INVSCALE
                underoft = baseline - metrics.get_underline_position(
                ) * PANGO_INVSCALE
                uth = h + underoft - 0.5 * underthick
                self.drawline(oft, uth, oft + tw, uth, underthick)
        return (tw, th)

    def text_left(self,
                  w,
                  h,
                  msg,
                  font=None,
                  strikethrough=False,
                  maxwidth=None,
                  underline=False):
        # TODO: replace with text_cell
        tw = 0
        th = self.line_height
        if msg:
            baseline = _CELL_BASELINE * self.line_height

            l = Pango.Layout.new(self.p)
            l.set_alignment(Pango.Alignment.LEFT)
            if font is not None:
                l.set_font_description(font)
            l.set_text(msg, -1)
            intr, logr = l.get_extents()
            fnbaseline = l.get_baseline() * PANGO_INVSCALE
            thof = logr.y * PANGO_INVSCALE
            twof = logr.x * PANGO_INVSCALE
            tw = logr.width * PANGO_INVSCALE
            th = logr.height * PANGO_INVSCALE
            oft = w + twof
            self.c.move_to(oft, h + (baseline - fnbaseline) + thof)
            PangoCairo.update_context(self.c, self.p)
            l.context_changed()
            PangoCairo.show_layout(self.c, l)

            metrics = None
            if underline or strikethrough:
                metrics = l.get_context().get_metrics(font)
            if strikethrough:
                strikethick = metrics.get_strikethrough_thickness(
                ) * PANGO_INVSCALE
                strikeoft = baseline - metrics.get_strikethrough_position(
                ) * PANGO_INVSCALE
                sth = h + strikeoft - 0.5 * strikethick
                self.drawline(oft, sth, oft + tw, sth, strikethick)
            if underline:
                underthick = metrics.get_underline_thickness() * PANGO_INVSCALE
                underoft = baseline - metrics.get_underline_position(
                ) * PANGO_INVSCALE
                uth = h + underoft - 0.5 * underthick
                self.drawline(oft, uth, oft + tw, uth, underthick)
        return (tw, th)

    def gtext_left(self,
                   w,
                   h,
                   msg,
                   font=None,
                   strikethrough=False,
                   maxwidth=None,
                   underline=False):
        # TODO: replace with text_cell
        tw = 0
        th = self.line_height
        if msg:
            baseline = _CELL_BASELINE * self.line_height

            l = Pango.Layout.new(self.p)
            l.set_alignment(Pango.Alignment.LEFT)
            if font is not None:
                l.set_font_description(font)
            l.set_text(msg, -1)
            intr, logr = l.get_extents()
            fnbaseline = l.get_baseline() * PANGO_INVSCALE
            thof = logr.y * PANGO_INVSCALE
            twof = logr.x * PANGO_INVSCALE
            tw = logr.width * PANGO_INVSCALE
            th = logr.height * PANGO_INVSCALE
            oft = w + twof
            self.c.move_to(oft, h)
            #self.c.move_to(oft, h + (baseline - fnbaseline) + thof)
            PangoCairo.update_context(self.c, self.p)
            l.context_changed()
            PangoCairo.show_layout(self.c, l)

            metrics = None
            if underline or strikethrough:
                metrics = l.get_context().get_metrics(font)
            if strikethrough:
                strikethick = metrics.get_strikethrough_thickness(
                ) * PANGO_INVSCALE
                strikeoft = baseline - metrics.get_strikethrough_position(
                ) * PANGO_INVSCALE
                sth = h + strikeoft - 0.5 * strikethick
                self.drawline(oft, sth, oft + tw, sth, strikethick)
            if underline:
                underthick = metrics.get_underline_thickness() * PANGO_INVSCALE
                underoft = baseline - metrics.get_underline_position(
                ) * PANGO_INVSCALE
                uth = h + underoft - 0.5 * underthick
                self.drawline(oft, uth, oft + tw, uth, underthick)
        return (tw, th)

    def text_para(self,
                  w,
                  h,
                  text,
                  font=None,
                  width=None,
                  halign=Pango.Alignment.LEFT):
        tw = 0
        th = self.line_height
        if text:
            if width is None:
                width = self.body_width
            l = Pango.Layout.new(self.p)
            if font is not None:
                l.set_font_description(font)
            l.set_width(int(Pango.SCALE * width + 1))
            l.set_wrap(Pango.WrapMode.WORD)
            l.set_alignment(halign)
            l.set_text(text, -1)
            (tw, th) = l.get_pixel_size()
            self.c.move_to(w, h)
            PangoCairo.update_context(self.c, self.p)
            l.context_changed()
            PangoCairo.show_layout(self.c, l)
        return (tw, th)

    def text_cent(self, w, h, msg, font=None, halign=Pango.Alignment.CENTER):
        # TODO: Replace with text_box
        tw = 0
        th = self.line_height
        if msg:
            l = Pango.Layout.new(self.p)
            l.set_alignment(halign)
            if font is not None:
                l.set_font_description(font)
            l.set_text(msg, -1)
            (tw, th) = l.get_pixel_size()
            self.c.move_to(w - (0.5 * tw), h)
            PangoCairo.update_context(self.c, self.p)
            l.context_changed()
            PangoCairo.show_layout(self.c, l)
        return (tw, th)

    def text_path(self, w, h, msg, font=None):
        tw = 0
        th = self.line_height
        if msg:
            l = Pango.Layout.new(self.p)
            if font is not None:
                l.set_font_description(font)
            l.set_text(msg, -1)
            (tw, th) = l.get_pixel_size()
            self.c.move_to(w - (0.5 * tw), h)
            PangoCairo.update_context(self.c, self.p)
            l.context_changed()
            PangoCairo.layout_path(self.c, l)
            self.c.fill()
        return (tw, th)

    def draw_provisional(self):
        self.c.save()
        self.c.set_source_rgb(1.0, 1.0, 1.0)
        self.text_cent(self.midpagew, self.body_top - mm2pt(5), 'PROVISIONAL',
                       self.fonts['body'])
        self.c.set_source_rgb(0.90, 0.90, 0.90)
        self.c.rectangle(self.body_left - 20, self.body_top - 20,
                         self.body_right - self.body_left + 40,
                         self.body_bot - self.body_top + 40)
        self.c.clip()
        self.c.translate(self.midpagew, self.midpageh)
        self.c.rotate(0.95532)
        self.text_path(
            0, -380,
            'PROVISIONAL\nPROVISIONAL\nPROVISIONAL\nPROVISIONAL\nPROVISIONAL',
            self.fonts['provisional'])
        self.c.restore()
