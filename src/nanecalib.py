#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# This file is part of nanecalib 
#
# Copyright (c) 2020 Lorenzo Carbonell Cerezo <a.k.a. atareao>
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.


import gi
try:
    gi.require_version('Gtk', '3.0')
    gi.require_version('Gdk', '3.0')
    gi.require_version('GLib', '2.0')
    gi.require_version('GObject', '2.0')
except Exception as e:
    print(e)
    exit(-1)
from gi.repository import Gtk
from gi.repository import Gdk
from gi.repository import GLib
from gi.repository import GObject
import os
from concurrent import futures


class Progreso(Gtk.Dialog):
    __gsignals__ = {
        'i-want-stop': (GObject.SIGNAL_RUN_FIRST, GObject.TYPE_NONE, ()),
    }

    def __init__(self, title, parent, icon=None):
        Gtk.Dialog.__init__(self, title, parent)
        self.set_modal(True)
        self.set_destroy_with_parent(True)
        self.set_resizable(False)
        if icon:
            self.set_icon_name(icon)
        self.set_size_request(330, 30)
        self.connect('destroy', self.close)
        self.connect('realize', self.on_realize)
        self.init_ui()
        self.stop = False
        self.show_all()
        self.value = 0.0

    def init_ui(self):
        vbox = Gtk.Box(Gtk.Orientation.VERTICAL, 5)
        vbox.set_border_width(5)
        self.get_content_area().add(vbox)

        frame1 = Gtk.Frame()
        vbox.add(frame1)

        grid = Gtk.Grid()
        grid.set_row_spacing(10)
        grid.set_column_spacing(10)
        grid.set_margin_bottom(10)
        grid.set_margin_start(10)
        grid.set_margin_end(10)
        grid.set_margin_top(10)
        frame1.add(grid)

        self.label = Gtk.Label()
        grid.attach(self.label, 0, 0, 2, 1)

        self.progressbar = Gtk.ProgressBar()
        self.progressbar.set_size_request(300, 0)
        grid.attach(self.progressbar, 0, 1, 1, 1)

        button_stop = Gtk.Button()
        button_stop.set_size_request(40, 40)
        button_stop.set_image(
            Gtk.Image.new_from_stock(Gtk.STOCK_STOP, Gtk.IconSize.BUTTON))
        button_stop.connect('clicked', self.on_button_stop_clicked)
        grid.attach(button_stop, 1, 1, 1, 1)

    def on_realize(self, *_):
        display = Gdk.Display.get_default()
        seat = display.get_default_seat()
        pointer = seat.get_pointer()
        screen, x, y = pointer.get_position()
        monitor = display.get_monitor_at_point(x, y)
        scale = monitor.get_scale_factor()
        monitor_width = monitor.get_geometry().width / scale
        monitor_height = monitor.get_geometry().height / scale
        width = self.get_preferred_width()[0]
        height = self.get_preferred_height()[0]
        self.move((monitor_width - width)/2, (monitor_height - height)/2)

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
        self.value += float(x)
        if round(self.value, 5) >= 1.0:
            GLib.idle_add(self.destroy)
        else:
            GLib.idle_add(self.progressbar.set_fraction, self.value)

    def set_element(self, widget=None, element=''):
        GLib.idle_add(self.label.set_text, str(element))


class DoItInBackground(GObject.GObject):
    __gsignals__ = {
        'started': (GObject.SIGNAL_RUN_FIRST, GObject.TYPE_NONE, (int,)),
        'ended': (GObject.SIGNAL_RUN_FIRST, GObject.TYPE_NONE, (bool,)),
        'start_one': (GObject.SIGNAL_RUN_FIRST, GObject.TYPE_NONE, (str,)),
        'end_one': (GObject.SIGNAL_RUN_FIRST, GObject.TYPE_NONE, (float,)),
    }

    def __init__(self, title, parent, files, icon=None):
        GObject.GObject.__init__(self)
        self.files = files
        self.stopit = False
        self.ok = True
        self.total_duration = self.get_total_duration(files)
        self.progreso = Progreso(title, parent, icon)
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
            executor = futures.ThreadPoolExecutor()
            for afile in self.files:
                if self.stopit is True:
                    break
                task = executor.submit(self.__process_item, afile)
                self.tasks.append({'file': afile,
                                   'task': task})
            if self.stopit is True:
                for task in self.tasks:
                    if task['task'].is_running():
                        task['task'].cancel()
                        duration = self.get_duration(task['file'])
                        self.emit(
                            'end_one',
                            duration / self.total_duration)
            self.progreso.run()
        except Exception as e:
            self.ok = False
            print(e)
        self.emit('ended', self.ok)

    def get_total_duration(self, files):
        total_duration = 0.0
        for afile in files:
            total_duration += float(os.path.getsize(afile))
        return total_duration

    def get_duration(self, file_in):
        return float(os.path.getsize(file_in))

    def __process_item(self, file_in):
        duration = self.get_duration(file_in)
        self.emit('start_one', os.path.basename(file_in))
        self.process_item(file_in)
        self.emit('end_one', duration / self.total_duration)

    def process_item(self, file_in):
        pass
