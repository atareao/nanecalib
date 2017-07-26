#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# This file is part of nautilus-convert2ogg
#
# Copyright (C) 2012-2016 Lorenzo Carbonell
# lorenzo.carbonell.cerezo@gmail.com
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
#
#
import gi
try:
    gi.require_version('Gtk', '3.0')
    gi.require_version('Gio', '2.0')
    gi.require_version('GLib', '2.0')
    gi.require_version('GObject', '2.0')
    gi.require_version('Nautilus', '3.0')
except Exception as e:
    print(e)
    exit(-1)
from gi.repository import Gtk
from gi.repository import Gio
from gi.repository import GLib
from gi.repository import GObject
from gi.repository import Nautilus as FileManager
import os
import subprocess
import shlex
from multiprocessing import cpu_count
from concurrent import futures

THREADS = 5 * cpu_count()
APPNAME = '$APP$'
ICON = '$APP$'
VERSION = '$VERSION$'

_ = str


class Progreso(Gtk.Dialog):
    __gsignals__ = {
        'i-want-stop': (GObject.SIGNAL_RUN_FIRST, GObject.TYPE_NONE, ()),
    }

    def __init__(self, title, parent):
        Gtk.Dialog.__init__(self, title, parent,
                            Gtk.DialogFlags.MODAL |
                            Gtk.DialogFlags.DESTROY_WITH_PARENT)
        self.set_position(Gtk.WindowPosition.CENTER_ALWAYS)
        self.set_size_request(330, 30)
        self.set_resizable(False)
        self.connect('destroy', self.close)
        self.set_modal(True)
        vbox = Gtk.VBox(spacing=5)
        vbox.set_border_width(5)
        self.get_content_area().add(vbox)
        #
        frame1 = Gtk.Frame()
        vbox.pack_start(frame1, True, True, 0)
        table = Gtk.Table(2, 2, False)
        frame1.add(table)
        #
        self.label = Gtk.Label()
        table.attach(self.label, 0, 2, 0, 1,
                     xpadding=5,
                     ypadding=5,
                     xoptions=Gtk.AttachOptions.SHRINK,
                     yoptions=Gtk.AttachOptions.EXPAND)
        #
        self.progressbar = Gtk.ProgressBar()
        self.progressbar.set_size_request(300, 0)
        table.attach(self.progressbar, 0, 1, 1, 2,
                     xpadding=5,
                     ypadding=5,
                     xoptions=Gtk.AttachOptions.SHRINK,
                     yoptions=Gtk.AttachOptions.EXPAND)
        button_stop = Gtk.Button()
        button_stop.set_size_request(40, 40)
        button_stop.set_image(
            Gtk.Image.new_from_stock(Gtk.STOCK_STOP, Gtk.IconSize.BUTTON))
        button_stop.connect('clicked', self.on_button_stop_clicked)
        table.attach(button_stop, 1, 2, 1, 2,
                     xpadding=5,
                     ypadding=5,
                     xoptions=Gtk.AttachOptions.SHRINK)
        self.stop = False
        self.fraction = 0.0
        self.is_running = False

        self.show_all()

    def emit(self, *args):
        GLib.idle_add(GObject.GObject.emit, self, *args)

    def get_stop(self):
        return self.stop

    def on_button_stop_clicked(self, widget):
        self.stop = True
        self.emit('i-want-stop')

    def close(self, *args):
        self.destroy()

    def increase(self, widget=None, x=1.0):
        self.fraction += float(x)
        if round(self.fraction, 5) >= 1.0:
            GLib.idle_add(self.destroy)
        else:
            GLib.idle_add(self.progressbar.set_fraction, self.fraction)

    def set_element(self, widget=None, element=''):
        GLib.idle_add(self.label.set_text, str(element))


def crush_file(file_in, diib):
    size = get_duration(file_in)
    diib.emit('start_one', os.path.basename(file_in))
    rutine = 'srm -lvr "%s"' % (file_in)
    args = shlex.split(rutine)
    process = subprocess.Popen(args, stdout=subprocess.PIPE)
    out, err = process.communicate()
    diib.emit('end_one', size / diib.total_size)


class DoItInBackground(GObject.GObject):
    __gsignals__ = {
        'started': (GObject.SIGNAL_RUN_FIRST, GObject.TYPE_NONE, (int,)),
        'ended': (GObject.SIGNAL_RUN_FIRST, GObject.TYPE_NONE, (bool,)),
        'start_one': (GObject.SIGNAL_RUN_FIRST, GObject.TYPE_NONE, (str,)),
        'end_one': (GObject.SIGNAL_RUN_FIRST, GObject.TYPE_NONE, (float,)),
    }

    def __init__(self, title, parent, files):
        GObject.GObject.__init__(self)
        self.files = files
        self.stopit = False
        self.ok = True
        self.total_size = get_total_duration(files)
        self.progreso = Progreso(title, parent)
        self.progreso.connect('i-want-stop', self.stop)
        self.connect('start_one', self.progreso.set_element)
        self.connect('end_one', self.progreso.increase)
        self.connect('ended', self.progreso.close)
        self.tasks = []

    def emit(self, *args):
        GLib.idle_add(GObject.GObject.emit, self, *args)

    def stop(self, *args):
        self.stopit = True

    def run(self):
        try:
            executor = futures.ThreadPoolExecutor(THREADS)
            for afile in self.files:
                if self.stopit is True:
                    break
                task = executor.submit(crush_file, afile, self)
                self.tasks.append({'file': afile,
                                   'task': task})
            if self.stopit is True:
                for task in self.tasks:
                    if task['task'].is_running():
                        task['task'].cancel()
                        self.emit('end_one',
                                  get_duration(task['file']) / self.total_size)
            self.progreso.run()
        except Exception as e:
            self.ok = False
            print(e)
        self.emit('ended', self.ok)


def get_total_duration(files):
    total_duration = 0.0
    for afile in files:
        total_duration += float(os.path.getsize(afile))
    return total_duration


def get_duration(file_in):
    return float(os.path.getsize(file_in))


def get_files(files_in):
    files = []
    gvfs = Gio.Vfs.get_default()
    for file_in in files_in:
        print(type(file_in), file_in)
        files.append(gvfs.get_file_for_uri(file_in.get_uri()).get_path())
    return files


class CrushFileMenuProvider(GObject.GObject, FileManager.MenuProvider):
    """
    Implements the 'Replace in Filenames' extension to the File Manager\
    right-click menu
    """

    def __init__(self):
        """
        File Manager crashes if a plugin doesn't implement the __init__\
        method
        """
        pass

    def all_are_files(self, items):
        gvfs = Gio.Vfs.get_default()
        for item in items:
            file_in = gvfs.get_file_for_uri(item.get_uri()).get_path()
            if not os.path.isfile(file_in):
                return False
        return True

    def convert(self, menu, selected, window):
        files = get_files(selected)
        diib = DoItInBackground(_('Crush file'), window, files)
        diib.run()

    def get_file_items(self, window, sel_items):
        """
        Adds the 'Replace in Filenames' menu item to the File Manager\
        right-click menu, connects its 'activate' signal to the 'run'\
        method passing the selected Directory/File
        """
        if self.all_are_files(sel_items):
            top_menuitem = FileManager.MenuItem(
                name='CrushFileMenuProvider::Gtk-crushing-top',
                label=_('Crush') + '...',
                tip=_('Tool to crush files'))
            submenu = FileManager.Menu()
            top_menuitem.set_submenu(submenu)

            sub_menuitem_00 = FileManager.MenuItem(
                name='CrushFileMenuProvider::Gtk-crushing-sub-01',
                label=_('Crush'),
                tip=_('Tool to crush files'))
            sub_menuitem_00.connect('activate',
                                    self.convert,
                                    sel_items,
                                    window)
            submenu.append_item(sub_menuitem_00)
            sub_menuitem_01 = FileManager.MenuItem(
                name='CrushFileMenuProvider::Gtk-crushing-sub-02',
                label=_('About'),
                tip=_('About'))
            sub_menuitem_01.connect('activate', self.about, window)
            submenu.append_item(sub_menuitem_01)
            #
            return top_menuitem,
        return

    def about(self, widget, window):
        ad = Gtk.AboutDialog(parent=window)
        ad.set_name(APPNAME)
        ad.set_version(VERSION)
        ad.set_copyright('Copyrignt (c) 2016-2017\nLorenzo Carbonell')
        ad.set_comments(APPNAME)
        ad.set_license('''
This program is free software: you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version.

This program is distributed in the hope that it will be useful, but WITHOUT
ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with
this program. If not, see <http://www.gnu.org/licenses/>.
''')
        ad.set_website('http://www.atareao.es')
        ad.set_website_label('http://www.atareao.es')
        ad.set_authors([
            'Lorenzo Carbonell <lorenzo.carbonell.cerezo@gmail.com>'])
        ad.set_documenters([
            'Lorenzo Carbonell <lorenzo.carbonell.cerezo@gmail.com>'])
        ad.set_icon_name(ICON)
        ad.set_logo_icon_name(APPNAME)
        ad.run()
        ad.destroy()
