"""Shared UI helper functions."""

import os
import gi

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

gi.require_version('Pango', '1.0')
from gi.repository import Pango
import metarace
from metarace import tod
from metarace import strops

# Font-overrides
DIGITFONT = Pango.FontDescription('Noto Mono Medium 22')
MONOFONT = Pango.FontDescription('Noto Mono')
LOGVIEWFONT = Pango.FontDescription('Noto Mono 11')

# Button indications
with metarace.resource_file('bg_idle.svg') as fn:
    bg_none = Gtk.Image.new_from_file(str(fn))
with metarace.resource_file('bg_armstart.svg') as fn:
    bg_armstart = Gtk.Image.new_from_file(str(fn))
with metarace.resource_file('bg_armint.svg') as fn:
    bg_armint = Gtk.Image.new_from_file(str(fn))
with metarace.resource_file('bg_armfin.svg') as fn:
    bg_armfin = Gtk.Image.new_from_file(str(fn))


def hvscroller(child):
    """Return a new scrolled window packed with the supplied child."""
    vs = Gtk.ScrolledWindow()
    vs.show()
    vs.set_border_width(5)
    vs.set_shadow_type(Gtk.ShadowType.IN)
    vs.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    vs.add(child)
    return vs


def vscroller(child):
    """Return a new scrolled window packed with the supplied child."""
    vs = Gtk.ScrolledWindow()
    vs.show()
    vs.set_border_width(5)
    vs.set_shadow_type(Gtk.ShadowType.IN)
    vs.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    vs.add(child)
    return vs


class statbut(object):

    def __init__(self, b=None):
        c = Gtk.HBox(spacing=2)
        self._i = Gtk.Image.new_from_pixbuf(bg_none.get_pixbuf())
        self._i.show()
        c.pack_start(self._i, False, True, 0)
        self._l = Gtk.Label(label='Idle')
        self._l.show()
        c.pack_start(self._l, True, True, 0)
        c.show()
        b.add(c)
        self._b = b

    def buttonchg(self, image, label=None):
        self._i.set_from_pixbuf(image.get_pixbuf())
        if label is not None:
            self._l.set_text(label)

    def set_sensitive(self, sensitive=False):
        self._b.set_sensitive(sensitive)


def mkviewcoltod(view=None,
                 header='',
                 cb=None,
                 width=120,
                 editcb=None,
                 colno=None):
    """Return a Time of Day view column."""
    i = Gtk.CellRendererText()
    i.set_property('xalign', 1.0)
    j = Gtk.TreeViewColumn(header, i)
    j.set_cell_data_func(i, cb, colno)
    if editcb is not None:
        i.set_property('editable', True)
        i.connect('edited', editcb, colno)
    j.set_min_width(width)
    view.append_column(j)
    return j


def mkviewcoltxt(view=None,
                 header='',
                 colno=None,
                 cb=None,
                 width=None,
                 halign=None,
                 calign=None,
                 expand=False,
                 editcb=None,
                 maxwidth=None,
                 bgcol=None,
                 fontdesc=None,
                 fixed=False):
    """Return a text view column."""
    i = Gtk.CellRendererText()
    if cb is not None:
        i.set_property('editable', True)
        i.connect('edited', cb, colno)
    if calign is not None:
        i.set_property('xalign', calign)
    if fontdesc is not None:
        i.set_property('font_desc', fontdesc)
    j = Gtk.TreeViewColumn(header, i, text=colno)
    if bgcol is not None:
        j.add_attribute(i, 'background', bgcol)
    if halign is not None:
        j.set_alignment(halign)
    if fixed:
        j.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
    if expand:
        if width is not None:
            j.set_min_width(width)
        j.set_expand(True)
    else:
        if width is not None:
            j.set_min_width(width)
    if maxwidth is not None:
        j.set_max_width(maxwidth)
    view.append_column(j)
    if editcb is not None:
        i.connect('editing-started', editcb)
    return i


def mkviewcolbg(view=None,
                header='',
                colno=None,
                cb=None,
                width=None,
                halign=None,
                calign=None,
                expand=False,
                editcb=None,
                maxwidth=None):
    """Return a text view column."""
    i = Gtk.CellRendererText()
    if cb is not None:
        i.set_property('editable', True)
        i.connect('edited', cb, colno)
    if calign is not None:
        i.set_property('xalign', calign)
    j = Gtk.TreeViewColumn(header, i, background=colno)
    if halign is not None:
        j.set_alignment(halign)
    if expand:
        if width is not None:
            j.set_min_width(width)
        j.set_expand(True)
    else:
        if width is not None:
            j.set_min_width(width)
    if maxwidth is not None:
        j.set_max_width(maxwidth)
    view.append_column(j)
    if editcb is not None:
        i.connect('editing-started', editcb)
    return i


def savecsvdlg(title='', parent=None, hintfile=None, lpath=None):
    ret = None
    dlg = Gtk.FileChooserDialog(title, parent, Gtk.FileChooserAction.SAVE,
                                (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                                 Gtk.STOCK_SAVE, Gtk.ResponseType.OK))
    cfilt = Gtk.FileFilter()
    cfilt.set_name('CSV Files')
    cfilt.add_mime_type('text/csv')
    cfilt.add_pattern('*.csv')
    dlg.add_filter(cfilt)
    cfilt = Gtk.FileFilter()
    cfilt.set_name('All Files')
    cfilt.add_pattern('*')
    dlg.add_filter(cfilt)
    if lpath:
        dlg.set_current_folder(lpath)
    if hintfile:
        dlg.set_current_name(hintfile)
    response = dlg.run()
    if response == Gtk.ResponseType.OK:
        ret = dlg.get_filename()
    dlg.destroy()
    return ret


def loadcsvdlg(title='', parent=None, lpath=None):
    ret = None
    dlg = Gtk.FileChooserDialog(title, parent, Gtk.FileChooserAction.OPEN,
                                (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                                 Gtk.STOCK_OPEN, Gtk.ResponseType.OK))
    cfilt = Gtk.FileFilter()
    cfilt.set_name('CSV Files')
    cfilt.add_mime_type('text/csv')
    cfilt.add_pattern('*.csv')
    dlg.add_filter(cfilt)
    cfilt = Gtk.FileFilter()
    cfilt.set_name('All Files')
    cfilt.add_pattern('*')
    dlg.add_filter(cfilt)
    if lpath:
        dlg.set_current_folder(lpath)
    response = dlg.run()
    if response == Gtk.ResponseType.OK:
        ret = dlg.get_filename()
    dlg.destroy()
    return ret


def mkviewcolbool(view=None,
                  header='',
                  colno=None,
                  cb=None,
                  width=None,
                  expand=False):
    """Return a boolean view column."""
    i = Gtk.CellRendererToggle()
    i.set_property('activatable', True)
    if cb is not None:
        i.connect('toggled', cb, colno)
    j = Gtk.TreeViewColumn(header, i, active=colno)
    if expand:
        j.set_min_width(width)
        j.set_expand(True)
    else:
        if width is not None:
            j.set_min_width(width)
    view.append_column(j)
    return i


def coltxtbibser(col, cr, model, iter, data):
    """Display a bib.ser string in a tree view."""
    (bibcol, sercol) = data
    cr.set_property(
        'text',
        strops.bibser2bibstr(model.get_value(iter, bibcol),
                             model.get_value(iter, sercol)))


def mkviewcolbibser(view=None,
                    header='No.',
                    bibno=0,
                    serno=1,
                    width=None,
                    expand=False):
    """Return a column to display bib/series as a bib.ser string."""
    i = Gtk.CellRendererText()
    i.set_property('xalign', 1.0)
    j = Gtk.TreeViewColumn(header, i)
    j.set_cell_data_func(i, coltxtbibser, (bibno, serno))
    if expand:
        j.set_min_width(width)
        j.set_expand(True)
    else:
        if width is not None:
            j.set_min_width(width)
    view.append_column(j)
    return i


def mktextentry(prompt, row, table):
    """Create and return a text entry within a gtk table."""
    if '?' not in prompt:
        prompt += ':'
    l = Gtk.Label(label=prompt)
    l.set_alignment(0.0, 0.5)
    l.show()
    table.attach(l,
                 0,
                 1,
                 row,
                 row + 1,
                 Gtk.AttachOptions.FILL,
                 Gtk.AttachOptions.FILL,
                 xpadding=5)
    e = Gtk.Entry()
    e.set_width_chars(24)
    e.set_activates_default(True)  # Check assumption on window
    e.show()
    table.attach(e,
                 1,
                 2,
                 row,
                 row + 1,
                 Gtk.AttachOptions.FILL | Gtk.AttachOptions.EXPAND,
                 Gtk.AttachOptions.FILL,
                 xpadding=5,
                 ypadding=2)
    return e


def mkcomboentry(prompt, row, table, options):
    """Create and return a combo entry within a gtk table."""
    l = Gtk.Label(label=prompt)
    l.set_alignment(1.0, 0.5)
    l.show()
    table.attach(l,
                 0,
                 1,
                 row,
                 row + 1,
                 Gtk.AttachOptions.FILL,
                 Gtk.AttachOptions.FILL,
                 xpadding=5)
    c = Gtk.ComboBoxText()
    c.show()
    for opt in options:
        c.append_text(opt)
    table.attach(c,
                 1,
                 2,
                 row,
                 row + 1,
                 Gtk.AttachOptions.FILL,
                 Gtk.AttachOptions.FILL,
                 xpadding=5)
    return c


def mklbl(prompt, row, table):
    """Create and return label within a gtk table."""
    l = Gtk.Label(label=prompt)
    l.set_alignment(1.0, 0.5)
    l.show()
    table.attach(l,
                 0,
                 1,
                 row,
                 row + 1,
                 Gtk.AttachOptions.FILL,
                 Gtk.AttachOptions.FILL,
                 xpadding=5)
    e = Gtk.Label()
    e.set_alignment(0.0, 0.5)
    e.show()
    table.attach(e,
                 1,
                 2,
                 row,
                 row + 1,
                 Gtk.AttachOptions.FILL,
                 Gtk.AttachOptions.FILL,
                 xpadding=5)
    return e


def mkbutintbl(prompt, row, col, table):
    """Create and return button within a gtk table."""
    b = Gtk.Button(prompt)
    b.show()
    table.attach(b,
                 col,
                 col + 1,
                 row,
                 row + 1,
                 Gtk.AttachOptions.FILL,
                 Gtk.AttachOptions.FILL,
                 xpadding=5,
                 ypadding=5)
    return b


def questiondlg(window, question, subtext=None):
    """Display a question dialog and return True/False."""
    dlg = Gtk.MessageDialog(window, Gtk.DialogFlags.MODAL,
                            Gtk.MessageType.QUESTION, Gtk.ButtonsType.YES_NO,
                            question)
    if subtext is not None:
        dlg.format_secondary_text(subtext)
    ret = False
    response = dlg.run()
    if response == Gtk.ResponseType.YES:
        ret = True
    dlg.destroy()
    return ret


def now_button_clicked_cb(button, entry=None):
    """Copy the current time of day into the supplied entry."""
    if entry is not None:
        entry.set_text(tod.now().timestr())


def edit_times_dlg(window,
                   stxt=None,
                   ftxt=None,
                   btxt=None,
                   ptxt=None,
                   bonus=False,
                   penalty=False):
    """Display times edit dialog and return updated time strings."""
    b = Gtk.Builder.new_from_string(metarace.resource_text('edit_times.ui'),
                                    -1)
    dlg = b.get_object('timing')
    dlg.set_transient_for(window)

    se = b.get_object('timing_start_entry')
    se.modify_font(MONOFONT)
    if stxt is not None:
        se.set_text(stxt)
    b.get_object('timing_start_now').connect('clicked', now_button_clicked_cb,
                                             se)

    fe = b.get_object('timing_finish_entry')
    fe.modify_font(MONOFONT)
    if ftxt is not None:
        fe.set_text(ftxt)
    b.get_object('timing_finish_now').connect('clicked', now_button_clicked_cb,
                                              fe)

    be = b.get_object('timing_bonus_entry')
    be.modify_font(MONOFONT)
    if btxt is not None:
        be.set_text(btxt)
    if bonus:
        be.show()
        b.get_object('timing_bonus_label').show()

    pe = b.get_object('timing_penalty_entry')
    pe.modify_font(MONOFONT)
    if ptxt is not None:
        pe.set_text(ptxt)
    if penalty:
        pe.show()
        b.get_object('timing_penalty_label').show()

    ret = dlg.run()
    stxt = se.get_text().strip()
    ftxt = fe.get_text().strip()
    btxt = be.get_text().strip()
    ptxt = pe.get_text().strip()
    dlg.destroy()
    return (ret, stxt, ftxt, btxt, ptxt)
