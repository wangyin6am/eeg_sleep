"""Visual objects of sleep module.

This file contains and initialize visual objects (channel plot, spectrogram,
hypnogram, indicator, shortcuts)
"""
import numpy as np
import scipy.signal as scpsig
import itertools
import logging
import colorcet

from vispy import scene
import vispy.visuals.transforms as vist

from .marker import Markers
from visbrain.utils import (color2vb, PrepareData, cmap_to_glsl)
from visbrain.utils.sleep.event import _index_to_events
from visbrain.visuals import TopoMesh, TFmapsMesh
from visbrain.config import PROFILER
# from visbrain.gui.sleep.interface.ui_elements import ui_detection

logger = logging.getLogger('visbrain')

__all__ = ("Visuals")


"""
###############################################################################
# OBJECTS
###############################################################################
Classes below are used to create visual objects, display on sevral canvas :
- ChannelPlot : plot data (one signal per channel)
- Spectrogram : on a specific channel
- Hypnogram : sleep stages (can be optional)
"""


class Detection(object):
    """Create a detection object."""
    # wy纺锤波颜色
    def __init__(self, channels, time, spincol=None, remcol=None,
                 kccol=None, swcol=None, peakcol=None, mtcol=None,spinacol=None,spinbcol=None,
                 spinsym=None, remsym=None, kcsym=None, swsym=None,
                 peaksym=None, mtsym=None, parent=None, parent_hyp=None):
        """Init."""
        # wy 纺锤波方法
        self.items = ['Spindles', 'REM', 'K-complexes', 'Slow waves', 'Peaks',
                      'Muscle twitches', 'Spindles-a', 'Spindles-b', 'Artifact-EEG', 'Artifact-ECG']
        self.chans = channels
        self.dict = {}
        self.line = {}
        self.peaks = {}
        self.seg = {}
        # wy 纺锤波方法.
        col = {'Spindles': spincol, 'REM': remcol, 'K-complexes': kccol,
               'Slow waves': swcol, 'Peaks': peakcol, 'Muscle twitches': mtcol,
               'Spindles-a': spincol, 'Spindles-b':spinacol, 'Artifact-EEG':spinacol,
                'Artifact-ECG': spinbcol}
        sym = {'Spindles': spinsym, 'REM': remsym, 'K-complexes': kcsym,
               'Slow waves': swsym, 'Peaks': peaksym, 'Muscle twitches': mtsym,
               'Spindles-a':spinsym, 'Spindles-b':remsym, 'Artifact-EEG': spinsym,
               'Artifact-ECG': kcsym}
        self.time = time
        self.hyp = Markers(parent=parent_hyp)
        self.hyp.set_gl_state('translucent')
        for num, k in enumerate(self):
            self[k] = {'index': np.array([]), 'color': col[k[1]],
                       'connect': np.array([]), 'sym': sym[k[1]]}
            par = parent[self.chans.index(k[0])]
            if k[1] is not 'Peaks':
                self.line[k] = scene.visuals.Line(method='gl', parent=par,
                                                  color=col[k[1]])
                self.line[k].set_gl_state('translucent')
            else:
                pos = np.full((1, 3), -10., dtype=np.float32)
                self.peaks[k] = Markers(pos=pos, parent=par,
                                        face_color=col[k[1]])
                self.peaks[k].set_gl_state('translucent')

    def __iter__(self):
        it = itertools.product(self.chans, self.items)
        for k in it:
            yield k

    def __bool__(self):
        return any([bool(self[k]['index'].size) for k in self])

    def __setitem__(self, key, value):
        self.dict[key] = value

    def __getitem__(self, key):
        return self.dict[key]

    def build_line(self, data):
        """Build detections reports.

        Parameters
        ----------
        data : array_like
            Data vector for a spcefic channel.
        """
        for num, k in enumerate(self):
            if self[k]['index'].size:
                # Get the channel number :
                nb = self.chans.index(k[0])
                # Send data :
                if k[1] is 'Peaks':
                    # Get index and channel number :
                    index = self[k]['index'][:, 0]
                    z = np.full(len(index), 2., dtype=np.float32)
                    pos = np.vstack((self.time[index], data[nb, index], z)).T
                    self.peaks[k].set_data(pos=pos, edge_width=0.,
                                           face_color=self[k]['color'])
                else:
                    # Get index and channel number :
                    # wy 表格中去掉小于0的数
                    arr = self[k]['index']
                    # 创建布尔数组，小于0的项设置为True
                    mask = arr < 0
                    # 使用布尔数组对原始数组进行索引
                    arr = arr[~mask.any(axis=1)]
                    index = _index_to_events(arr)
                    z = np.full(index.shape, 2., dtype=np.float32)
                    # Build position vector :
                    pos = np.vstack((self.time[index], data[nb, index], z)).T
                    # Build connections :
                    connect = np.gradient(index) == 1.
                    connect[0], connect[-1] = True, False
                    self.line[k].set_data(pos=pos, width=4., connect=connect)

    def build_hyp(self, chan, types):
        """Build hypnogram report.

        Parameters
        ----------
        chan : str
            String name of the channel.
        types : str
            String name of the detection type.
        """
        # Get index :
        # wy 表格中去掉小于0的数
        index = self[(chan, types)]['index']
        # 创建布尔数组，小于0的项设置为True
        mask = index < 0
        # 使用布尔数组对原始数组进行索引
        index = index[~mask.any(axis=1)]
        # index = self[(chan, types)]['index']
        # Get only starting points :
        start = index[:, 0]
        y = np.full_like(start, 1.5, dtype=float)
        z = np.full_like(start, -2., dtype=float)
        pos = np.vstack((self.time[start], y, z)).T
        # Set hypnogram data :
        self.hyp.set_data(pos=pos, symbol=self[(chan, types)]['sym'],
                          face_color=self[(chan, types)]['color'],
                          edge_width=1.,
                          edge_color=self[(chan, types)]['color'])

    ## //wy
    def build_hyp_add(self, chan, types):
        """Build hypnogram report.

        Parameters
        ----------
        chan : str
            String name of the channel.
        types : str
            String name of the detection type.
        """
        # Get index :
        index = self[(chan, types)]['index']
        # Get only starting points :
        start = index[:, 0]
        y = np.full_like(start, 1.5, dtype=float)
        z = np.full_like(start, -2., dtype=float)
        pos = np.vstack((round(self.time[start]), y, z)).T
        # Set hypnogram data :
        self.hyp.set_data(pos=pos, symbol=self[(chan, types)]['sym'],
                          face_color=self[(chan, types)]['color'],
                          edge_width=1.,
                          edge_color=self[(chan, types)]['color'])
    ## wy//

    def visible(self, viz, chan, types):
        """Set channel visibility.

        Parameters
        ----------
        viz : bool
            Boolean value indicating if the plot have to be displayed.
        chan : str
            Channel name.
        types : str
            Detection type name.
        """
        self.hyp.visible = viz
        if types == 'Peaks':
            self.peaks[(chan, types)].visible = viz
        else:
            self.line[(chan, types)].visible = viz

    def delete(self, chan, types):
        """Delete data of a channel."""
        # Remove data from dict :
        self[(chan, types)]['index'] = np.array([])
        # Remove data from plot :
        pos = np.full((1, 3), -10., dtype=np.float32)
        if types == 'Peaks':
            self.peaks[(chan, types)].set_data(pos=pos)
        else:
            self.line[(chan, types)].set_data(pos=pos,
                                              connect=np.array([False]))
        # Remove data from hypnogram :
        self.hyp.set_data(pos=pos)

    def nonzero(self):
        """Return the list of channels with non-empty detections."""
        chans = {}
        for k in self.chans:
            types = []
            for i in self.items:
                if self[(k, i)]['index'].size:
                    types.append(i)
            if types:
                chans[k] = types
        return chans

    def update_keys(self, newkeys):
        """Update the keys of dictionaries."""
        # Get old keys :
        oldkeys = list(self.dict.keys())
        # Check that new keys lentgh has the same size as old keys :
        if len(newkeys) != len(self.chans):
            raise ValueError("The length of new keys must be the same as old"
                             "keys")
        for k in oldkeys:
            # Find index of channel :
            idx = self.chans.index(k[0])
            # Build new key :
            nkey = (newkeys[idx], k[1])
            # Update keys (if needed):
            if nkey not in oldkeys:
                # Update dict and line :
                self.dict[nkey] = self.dict[k]
                if k[1] is 'Peaks':
                    self.peaks[nkey] = self.peaks[k]
                    del self.peaks[k]
                else:
                    self.line[nkey] = self.line[k]
                    del self.line[k]
                # Remove old key :
                del self.dict[k]
        self.chans = newkeys

    def reset(self):
        """Reset all detections."""
        for k in self:
            self[k]['index'] = np.array([])

## wy 绘图
class ChannelPlot(PrepareData):
    """Plot each channel."""
    # wy color=(.2, .2, .2)
    def __init__(self, channels, time, color='(.2, .2, .2)', width=1.5,
                 color_detection='red', method='gl', camera=None,
                 parent=None, fcn=None):
        # Initialize PrepareData :
        PrepareData.__init__(self, axis=1)

        # Variables :
        self._camera = camera
        self._preproc_channel = -1
        self.rect = []
        self.width = width
        self.autoamp = False
        self._fcn = fcn
        self.visible = np.array([True] + [False] * (len(channels) - 1))
        self.consider = np.ones((len(channels),), dtype=bool)

        # Get color :
        self.color = color2vb(color)
        self.color_detection = color2vb(color_detection)

        # Create one line per channel :
        pos = np.zeros((1, 3), dtype=np.float32)
        self.mesh, self.report, self.grid, self.peak, self.scorwin_ind = \
            [], [], [], [], []
        self.loc, self.node = [], []
        for i, k in enumerate(channels):
            # ----------------------------------------------
            # Create a node parent :
            node = scene.Node(name=k + 'plot')
            node.parent = parent[i].wc.scene
            self.node.append(node)

            # ----------------------------------------------
            # Create main line (for channel plot) :
            mesh = scene.visuals.Line(pos, name=k + 'plot', color=self.color,
                                      method=method, parent=node)
            mesh.set_gl_state('translucent')
            self.mesh.append(mesh)

            # ----------------------------------------------
            # Create marker peaks :
            mark = Markers(pos=np.zeros((1, 3), dtype=np.float32),
                           parent=node)
            mark.set_gl_state('translucent')
            mark.visible = False
            self.peak.append(mark)

            # ----------------------------------------------
            # Locations :
            loc = scene.visuals.Line(pos, name=k + 'location', method=method,
                                     color=(.1, .1, .1, .3), parent=node,
                                     connect='segments')
            loc.set_gl_state('translucent')
            self.loc.append(loc)

            # ----------------------------------------------
            # Create a grid :
            grid = scene.visuals.GridLines(color=(.1, .1, .1, .5),
                                           scale=(1., .1),
                                           parent=parent[i].wc.scene)
            grid.set_gl_state('translucent')
            self.grid.append(grid)

            # ----------------------------------------------
            # Create a scoring window indicator :
            scorwin_ind = ScorWinIndicator(parent=node,
                                           name=k + '_scorwin_ind',
                                           visible=True)
            self.scorwin_ind.append(scorwin_ind)

    def __iter__(self):
        """Iterate over visible mesh."""
        for i, k in enumerate(self.mesh):
            if self.visible[i]:
                yield i, k

    def __len__(self):
        """Return the number of channels."""
        return len(self.mesh)
    #
    def set_data(self, sf, data, time, sl=None, ylim=None, autoamp=True):
        """Set data to channels.

        Parameters
        ----------
        data: array_like
            Array of data of shape (n_channels, n_points)
        time: array_like
            The time vector.
        sl : slice | None
            A slice object for the time selection of data.
        ylim : array_like | None
            Y-limits of each channel. Must be a (n_channels, 2) array.
        """
        if ylim is None:
            ylim = np.array([data.min(1), data.max(1)]).T

        # Manage slice :
        sl = slice(0, data.shape[1]) if sl is None else sl

        # Slice selection (of time and data) :
        time_sl = time[sl]
        self.x = (time_sl.min(), time_sl.max())
        data_sl = data[self.visible, sl]
        z = np.full_like(time_sl, .5, dtype=np.float32)

        # Prepare the data (only if needed) :
        if self:
            if self._preproc_channel == -1:  # prepare all channels
                data_sl = self._prepare_data(sf, data_sl.copy(), time_sl)
            else:  # filt only one channel
                # Get on which visible channel to apply preprocessing :
                chan_lst_viz = list(np.arange(len(self))[self.visible])
                to_chan = chan_lst_viz.index(self._preproc_channel)
                data_sl[[to_chan], :] = self._prepare_data(sf, data_sl[
                    [to_chan], :].copy(), time_sl)

        # Set data to each plot :
        for l, (i, k) in enumerate(self):
            # ________ MAIN DATA ________
            # Select channel ;
            datchan = data_sl[l, :]

            # Concatenate time / data / z axis :
            dat = np.vstack((time_sl, datchan, z)).T

            # Set main ligne :
            k.set_data(dat, width=self.width)

            # ________ CAMERA ________
            # Use either auto / fixed adaptative camera :
            ycam = (datchan.min(), datchan.max()) if self.autoamp else ylim[i]

            # Get camera rectangle and set it:
            rect = (self.x[0], ycam[0], self.x[1] - self.x[0],
                    ycam[1] - ycam[0])
            self._camera[i].rect = rect
            k.update()
            self.rect.append(rect)

    def set_location(self, sf, data, channel, start, end, factor=100.):
        """Set vertical lines for detections."""
        # Get data limits :
        y = (data.min(), data.max())
        # # Build pos :
        pos = np.zeros((4, 3), dtype=np.float32)
        pos[0, 0:2] = [start, y[0]]
        pos[1, 0:2] = [start, y[1]]
        pos[2, 0:2] = [end, y[0]]
        pos[3, 0:2] = [end, y[1]]
        # Set data pos :
        self.loc[channel].set_data(pos=pos, width=2.)

    def clean(self):
        """Clean all the data."""
        # Empty position :
        pos = np.zeros((1, 3), dtype=np.float32)
        for k in range(len(self)):
            # Main mesh :
            self.mesh[k].set_data(pos=pos, color='gray')
            self.mesh[k].parent = None
            # Report :
            self.report[k].set_data(pos=pos, color='gray')
            self.report[k].parent = None
            # Grid :
            self.grid[k].parent = None
            # Peak locations :
            self.peak[k].set_data(pos=pos, face_color='gray')
            self.peak[k].parent = None
            # Vertical lines :
            self.loc[k].set_data(pos=pos, color='gray')
            self.loc[k].parent = None
        self.mesh, self.report, self.grid, self.peak = [], [], [], []
        self.loc = []

    # ----------- PARENT -----------
    @property
    def parent(self):
        """Get the parent value."""
        return self.mesh[0].parent

    @parent.setter
    def parent(self, value):
        """Set parent value."""
        for i, k, in zip(value, self.mesh):
            k.parent = i.wc.scene

    # ----------- AUTOAMP -----------
    @property
    def autoamp(self):
        """Get the autoamp value."""
        return self._autoamp

    @autoamp.setter
    def autoamp(self, value):
        """Set autoamp value."""
        self._autoamp = value


class Spectrogram(PrepareData):
    """Create and manage a Spectrogram object.

    After object creation, use the set_data() method to pass new data, new
    color, new frequency / time range, new settings...
    """

    def __init__(self, camera, parent=None, fcn=None):
        # Initialize PrepareData :
        PrepareData.__init__(self, axis=0)

        # Keep camera :
        self._camera = camera
        self._rect = (0., 0., 0., 0.)
        self._fcn = fcn

        # Time-frequency map
        self.tf = TFmapsMesh(parent=parent)
        # Spectrogram
        self.mesh = scene.visuals.Image(np.zeros((2, 2)), parent=parent,
                                        name='Fourier transform')
        self.mesh.transform = vist.STTransform()

    def set_data(self, sf, data, time, method='Fourier transform',
                 cmap='rainbow', nfft=30., overlap=0., fstart=.5, fend=20.,
                 contrast=.5, interp='nearest', norm=0):
        """Set data to the spectrogram.

        Use this method to change data, colormap, spectrogram settings, the
        starting and ending frequencies.

        Parameters
        ----------
        sf: float
            The sampling frequency.
        data: array_like
            The data to use for the spectrogram. Must be a row vector.
        time: array_like
            The time vector.
        method: string | 'Fourier transform'
            Computation method.
        cmap : string | 'viridis'
            The matplotlib colormap to use.
        nfft : float | 30.
            Number of fft points for the spectrogram (in seconds).
        overlap : float | .5
            Ovelap proprotion (0 <= overlap <1).
        fstart : float | .5
            Frequency from which the spectrogram have to start.
        fend : float | 20.
            Frequency from which the spectrogram have to finish.
        contrast : float | .5
            Contrast of the colormap.
        interp : string | 'nearest'
            Interpolation method.
        norm : int | 0
            Normalization method for TF.
        """
        # =================== PREPARE DATA ===================
        # Prepare data (only if needed)
        if self:
            data = self._prepare_data(sf, data.copy(), time)

        nperseg = int(round(nfft * sf))

        # =================== TF // SPECTRO ===================
        if method == 'Wavelet':
            self.tf.set_data(data, sf, f_min=fstart, f_max=fend, cmap=cmap,
                             contrast=contrast, n_window=nperseg,
                             overlap=overlap, window='hamming', norm=norm)
            self.tf._image.interpolation = interp
            self.rect = self.tf.rect
            self.freq = self.tf.freqs
        else:
            # =================== CONVERSION ===================
            overlap = int(round(overlap * nperseg))

            if method == 'Multitaper':
                from lspopt import spectrogram_lspopt
                freq, _, mesh = spectrogram_lspopt(data, fs=sf,
                                                   nperseg=nperseg,
                                                   c_parameter=20,
                                                   noverlap=overlap)
            elif method == 'Fourier transform':
                freq, _, mesh = scpsig.spectrogram(data, fs=sf,
                                                   nperseg=nperseg,
                                                   noverlap=overlap,
                                                   window='hamming')
            mesh = 20 * np.log10(mesh)

            # =================== FREQUENCY SELECTION ===================
            # Find where freq is [fstart, fend] :
            f = [0., 0.]
            f[0] = np.abs(freq - fstart).argmin() if fstart else 0
            f[1] = np.abs(freq - fend).argmin() if fend else len(freq)
            # Build slicing and select frequency vector :
            sls = slice(f[0], f[1] + 1)
            freq = freq[sls]
            self._fstart, self._fend = freq[0], freq[-1]

            # =================== COLOR ===================
            # Get clim :
            _mesh = mesh[sls, :]
            is_finite = np.isfinite(_mesh)
            _mesh[~is_finite] = np.percentile(_mesh[is_finite], 5)
            contrast = 1. if contrast is None else contrast
            clim = (contrast * _mesh.min(), contrast * _mesh.max())
            # Turn mesh into color array for selected frequencies:
            self.mesh.set_data(_mesh)
            _min, _max = _mesh.min(), _mesh.max()
            if cmap == 'rainbow':
                cmap = colorcet.cm['rainbow']
                _cmap = cmap_to_glsl(limits=(_min, _max), clim=clim, cmap=cmap)
            else:
                _cmap = cmap_to_glsl(limits=(_min, _max), clim=clim, cmap=cmap)
            self.mesh.cmap = _cmap
            self.mesh.clim = 'auto'
            self.mesh.interpolation = interp

            # =================== TRANSFORM ===================
            tm, th = time.min(), time.max()
            # Re-scale the mesh for fitting in time / frequency :
            fact = (freq.max() - freq.min()) / len(freq)
            sc = (th / mesh.shape[1], fact, 1)
            tr = [0., freq.min(), 0.]
            self.mesh.transform.translate = tr
            self.mesh.transform.scale = sc
            # Update object :
            self.mesh.update()
            # Get camera rectangle :
            self.rect = (tm, freq.min(), th - tm, freq.max() - freq.min())
            self.freq = freq
        # Visibility :
        self.mesh.visible = 0 if method == 'Wavelet' else 1
        self.tf.visible = 1 if method == 'Wavelet' else 0

    def clean(self):
        """Clean indicators."""
        pos = np.zeros((3, 4), dtype=np.float32)
        self.mesh.set_data(pos)
        self.mesh.parent = None
        self.mesh = None

    # ----------- RECT -----------
    @property
    def rect(self):
        """Get the rect value."""
        return self._rect

    @rect.setter
    def rect(self, value):
        """Set rect value."""
        self._rect = value
        self._camera.rect = value

    # ----------- INTERP -----------
    @property
    def interp(self):
        """Get the interp value."""
        return self._interp

    @interp.setter
    def interp(self, value):
        """Set interp value."""
        self._interp = value
        self.mesh.interpolation = value
        self.mesh.update()
        self.tf.interpolation = value
        self.tf.update()


class Hypnogram(object):
    """Create a hypnogram object."""

    def __init__(self, time, camera, color='#292824', width=2., parent=None,
                 hconv=None):
        # Keep camera :
        self._camera = camera
        self._rect = (0., 0., 0., 0.)
        self.rect = (time.min(), -5., time.max() - time.min(), 7.)
        self.width = width
        self.n = len(time)
        self._hconv = hconv
        self._hconvinv = {v: k for k, v in self._hconv.items()}
        # Get color :
        self.color = {k: color2vb(color=i) for k, i in zip(color.keys(),
                                                           color.values())}
        # Create a default line :
        pos = np.array([[0, 0], [0, 100]])
        self.mesh = scene.visuals.Line(pos, name='hypnogram', method='gl',
                                       parent=parent, width=width)
        self.mesh._width = width
        self.mesh.set_gl_state('translucent')

        # wy 第二睡眠标签
        self.mesh2 = scene.visuals.Line(pos, name='hypnogram', method='gl',
                                       parent=parent, width=width)
        self.mesh2._width = width
        self.mesh2.set_gl_state('translucent')
        # Create a default marker (for edition):
        self.edit = Markers(parent=parent)
        # self.mesh.set_gl_state('translucent', depth_test=True)
        self.edit.set_gl_state('translucent')
        # Add grid :
        self.grid = scene.visuals.GridLines(color=(.7, .7, .7, 1.),
                                            scale=(30. * time[-1] / len(time),
                                                   1.),
                                            parent=parent)
        self.grid.set_gl_state('translucent')

    def __len__(self):
        """Return the time length."""
        return self.n

    # -------------------------------------------------------------------------
    # SETTING METHODS
    # -------------------------------------------------------------------------
    def set_data(self, sf, data, time, convert=True):
        """Set data to the hypnogram.

        Parameters
        ----------
        sf: float
            The sampling frequency.
        data: array_like
            The data to send. Must be a row vector.
        time: array_like
            The time vector
        convert : bool | True
            Specify if hypnogram data have to be converted.
        """
        # Hypno conversion :
        if (self._hconv != self._hconvinv) and convert:
            data = self.hyp_to_gui(data)
        # Build color array :
        color = np.zeros((len(data), 4), dtype=np.float32)
        # color[:, :] = ((1, 0, 0, 1))
        # color[1::, :] = color[0:-1, :]
        for k, v in zip(self.color.keys(), self.color.values()):
            # Set the stage color :
            color[data == k, :] = v
        # Avoid gradient color :
        color[1::, :] = color[0:-1, :]
        # Set data to the mesh :
        self.mesh.set_data(pos=np.vstack((time, -data)).T, width=self.width,
                           color=color)
        self.mesh.update()
    # wy 第二睡眠标签
    def set_data2(self, sf, data, data_2, time, convert=True):

        if (self._hconv != self._hconvinv) and convert:
            data = self.hyp_to_gui(data)
            data_2 = self.hyp_to_gui(data_2)
        # Build color array :
        color = np.zeros((len(data), 4), dtype=np.float32)
        color_2 = np.zeros((len(data), 4), dtype=np.float32)
        # for k, v in zip(self.color.keys(), self.color.values()):
        #     # Set the stage color :
        #     color[data == k, :] = v
        # Avoid gradient color :
        # color[1::, :] = color[0:-1, :]
        color[:, :] = ((1, 0, 0, 1))
        color[1::, :] = color[0:-1, :]

        color_2[:, :]   = ((0.5, 0.5, 0.5, 1))
        color_2[1::, :] = color_2[0:-1, :]

        # Set data to the mesh :
        self.mesh.set_data(pos=np.vstack((time, -data)).T, width=self.width,
                           color=color)
        self.mesh2.set_data(pos=np.vstack((time, -data_2)).T, width=self.width,
                           color=color_2)
        self.mesh.update()
        self.mesh2.update()

    # wy 第二睡眠标签——独立
    def set_data3(self, sf, data, time, convert=True):

        if (self._hconv != self._hconvinv) and convert:
            data = self.hyp_to_gui(data)
        # Build color array :
        color = np.zeros((len(data), 4), dtype=np.float32)

        color[:, :] = ((0.5, 0.5, 0.5, 1))
        color[1::, :] = color[0:-1, :]

        # Set data to the mesh :
        self.mesh2.set_data(pos=np.vstack((time, -data)).T, width=self.width,
                           color=color)
        self.mesh2.update()

    def set_stage(self, stfrom, stend, stage):
        """Add a stage in a specific interval.

        This method only set the stage without updating the entire
        hypnogram.

        Parameters
        ----------
        stfrom : int
            The index where the stage start.
        stend : int
            The index where the stage end.
        stage : int
            Stage value.
        """
        # Convert the stage :
        stagec = self._hconv[stage]
        # Update color :
        self.mesh.color[stfrom + 1:stend + 1, :] = self.color[stagec]
        # Only update the needed part :
        self.mesh.pos[stfrom:stend, 1] = -float(stagec)
        self.mesh.update()

    def set_grid(self, time, length=30., y=1.):
        """Set grid lentgh."""
        # Get scaling factor :
        sc = (length * time[-1] / len(time), y)
        # Set to the grid :
        self.grid._grid_color_fn['scale'].value = sc
        self.grid.update()

    # -------------------------------------------------------------------------
    # CONVERSION METHODS
    # -------------------------------------------------------------------------
    def hyp_to_gui(self, data):
        """Convert hypnogram data to the GUI.

        Parameters
        ----------
        data : array_like
            The data to send. Must be a row vector.

        Returns
        -------
        datac : array_like
            Converted data
        """
        # Backup copy :
        datac = data.copy()
        data = np.zeros_like(datac)
        # Fill new data :
        for k in self._hconv.keys():
            data[datac == k] = self._hconv[k]
        return data

    def gui_to_hyp(self):
        """Convert GUI hypnogram into data.

        Returns
        -------
        data : array_like
            The converted data.
        """
        # Get latest data version :
        datac = -self.mesh.pos[:, 1]
        data = np.zeros_like(datac)
        # Fill new data :
        for k in self._hconvinv.keys():
            data[datac == k] = self._hconvinv[k]
        return data

    def clean(self, sf, time):
        """Clean indicators."""
        # Mesh :
        posmesh = np.zeros((len(self),), dtype=np.float32)
        self.set_data(sf, posmesh, time)
        # Edit :
        posedit = np.full((1, 3), -10., dtype=np.float32)
        self.edit.set_data(pos=posedit, face_color='gray')

    # ----------- RECT -----------
    @property
    def rect(self):
        """Get the rect value."""
        return self._rect

    @rect.setter
    def rect(self, value):
        """Set rect value."""
        self._rect = value
        self._camera.rect = value


"""
###############################################################################
# TOPOPLOT
###############################################################################
Topoplot class that inherit from the visual TopoMesh and PrepareData for
filetring, de-meaning...
"""


class TopoSleep(TopoMesh, PrepareData):
    """Topoplot for sleep data."""

    def __init__(self, **kwargs):
        # Initialize TopoMesh and PrepareData :
        TopoMesh.__init__(self, **kwargs)
        PrepareData.__init__(self, axis=1)
        # Initialize data, clim, cmap and cblabel :
        self._data = None
        self._clim = None
        self._cmap = None
        self._cblabel = None

    def set_sleep_topo(self, data=None, clim=None, cmap=None, cblabel=None):
        """Send data to TopoGraphic plot."""
        # Data :
        if data is None:
            data = self._data
        self._data = data
        # Clim :
        if clim is None:
            clim = self._clim
        self._clim = clim
        # Cmap :
        if cmap is None:
            cmap = self._cmap
        self._cmap = cmap
        # Cblabel :
        if cblabel is None:
            cblabel = self._cblabel
        self._cblabel = cblabel

        if data is not None:
            self.set_data(data, cmap=cmap, cblabel=cblabel, clim=clim)


"""
###############################################################################
# INDICATORS
###############################################################################
Visual indicators can be used to help the user to see in which time window the
signal is currently plotted. Those indicators are two vertical lines displayed
on the spectrogram and hypnogram.
"""


class Indicator(object):
    """Create a visual indicator (for spectrogram and hypnogram)."""

    def __init__(self, name='indicator', alpha=.3, visible=True, parent=None):
        # Create a vispy image object :
        image = color2vb('gray', alpha=alpha)[np.newaxis, ...]
        self.mesh = scene.visuals.Image(data=image, name=name,
                                        parent=parent)
        self.mesh.transform = vist.STTransform()
        self.mesh.visible = visible

    def set_data(self, xlim, ylim):
        """Move the visual indicator.

        Parameters
        ----------
        xlim : tuple
            A tuple of two float indicating where xlim start and xlim end.
        ylim : tuple
            A tuple of two floats indicating where ylim start and ylim end.
        """
        tox = (xlim[0], ylim[0], -1.)
        sc = (xlim[1] - xlim[0], ylim[1] - ylim[0], 1.)
        # Move the square
        self.mesh.transform.translate = tox
        self.mesh.transform.scale = sc

    def clean(self):
        """Clean indicators."""
        self.mesh.parent = None
        self.mesh = None


"""
###############################################################################
# SCORING WINDOW INDICATOR
###############################################################################
The scoring window indicators can be used to show the limits of the current
scoring window on each of the channel plots. On each of the channel plots, the
scoring window indicator consists in two vertical bars marking the start and
end of the window
"""


class ScorWinIndicator(object):
    """Create a visual indicator of scoring window (for channel plots)."""

    def __init__(self, name='scorwinindicator', alpha=.75, visible=True,
                 parent=None, color='red', barwidth=.20):
        # width of the vertical bars
        self.barwidth = barwidth
        # Create two vispy image object for the start and end of window
        # "Start mesh" : first vertical bar
        image_start = color2vb(color, alpha=alpha)[np.newaxis, ...]
        self.mesh_start = scene.visuals.Image(data=image_start, name=name,
                                              parent=parent)
        self.mesh_start.transform = vist.STTransform()
        self.mesh_start.visible = visible
        # "End mesh" : second vertical bar
        image_end = color2vb(color, alpha=alpha)[np.newaxis, ...]
        self.mesh_end = scene.visuals.Image(data=image_end, name=name,
                                            parent=parent)
        self.mesh_end.transform = vist.STTransform()
        self.mesh_end.visible = visible

    def set_data(self, x_start, x_end, ylim, barwidth=None):
        """Redraw the vertical bars

        Parameters
        ----------
        x_start: float
            A float indicating where the "start" bar is centered
        x_end: float
            A float indicating where the "end" bar is centered
        ylim : tuple
            A tuple of two floats indicating the vertical limits of both bars
        barwidth: float
            A float indicating the new width of the indicator bars
        """
        # Change barwidth
        if barwidth is not None:
            self.barwidth = barwidth
        # xlim of each bar
        xlim_start = (x_start - self.barwidth / 2, x_start + self.barwidth / 2)
        xlim_end = (x_end - self.barwidth / 2, x_end + self.barwidth / 2)
        # Displacement for each bar
        tox_start = (xlim_start[0], ylim[0], -1.)
        sc_start = (xlim_start[1] - xlim_start[0], ylim[1] - ylim[0], 1.)
        tox_end = (xlim_end[0], ylim[0], -1.)
        sc_end = (xlim_end[1] - xlim_end[0], ylim[1] - ylim[0], 1.)
        # Move the two bars
        self.mesh_start.transform.translate = tox_start
        self.mesh_start.transform.scale = sc_start
        self.mesh_end.transform.translate = tox_end
        self.mesh_end.transform.scale = sc_end

    def clean(self):
        """Clean indicators."""
        self.mesh_start.parent = None
        self.mesh_start = None
        self.mesh_end.parent = None
        self.mesh_end = None


"""
###############################################################################
# SHORTCUTS
###############################################################################
Shortcuts applied on each canvas.
"""


class CanvasShortcuts(object):
    """This class add some shortcuts to the main canvas.

    It's also use to initialize to panel of shortcuts.

    Parameters
    ----------
    canvas : vispy canvas
        Vispy canvas to add the shortcuts.
    """

    def __init__(self, canvas):
        """Init."""
        # wy
        self.sh = [('n', '下一页窗口'),
                   ('b', '上一页窗口'),
                   ('-', '降低幅度'),
                   ('+', '增加幅度'),
                   ('s', '显示/隐藏 spectrogram'),
                   ('t', '显示/隐藏 topoplot'),
                   ('h', '显示/隐藏 hypnogram'),
                   ('p', '显示/隐藏 navigation bar'),
                   ('x', '显示/隐藏 time axis'),
                   ('g', '显示/隐藏 time grid'),
                   ('z', '开启/关闭 zooming'),
                   ('i', '开启/关闭 indicators'),
                   ('a', '评分面板: 设置当前睡眠阶段为 Art (-1)'),
                   ('w', '评分面板: 设置当前睡眠阶段为 Wake (0)'),
                   ('1', '评分面板: 设置当前睡眠阶段为 N1 (1)'),
                   ('2', '评分面板: 设置当前睡眠阶段为 N2 (2)'),
                   ('3', '评分面板: 设置当前睡眠阶段为 N3 (3)'),
                   ('r', '评分面板: 设置当前睡眠阶段为 REM (4)'),
                   ('鼠标双击', '添加一条检测波形'),
                   ('ALT + 左键', '设置检测波形最后一行的结束值位置'),
                   ('CTRL + 左键', '放大该处信号波形'),
                   ('CTRL + Num', '显示通道个数'),
                   ('CTRL + s', '保存 hypnogram'),
                   ('CTRL + t', '显示快捷键'),
                   ('CTRL + e', '显示文档'),
                   ('CTRL + d', '显示/隐藏 设置面板'),
                   ('CTRL + n', '截屏'),
                   ('CTRL + q', '退出软件'),
                   ]

        # 键盘按快捷键触发的功能
        # Add shortcuts to vbCanvas :
        @canvas.events.key_press.connect
        def on_key_press(event):
            """Executed function when a key is pressed on a keyboard over canvas.

            :event: the trigger event
            """
            if event.text == ' ':
                pass

            # ------------ SLIDER ------------
            elif event.text.lower() == 'n':  # Next (slider)
                self._SlGoto.setValue(
                    self._SlGoto.value() + self._SigSlStep.value())
            elif event.text.lower() == 'b':  # Before (slider)
                self._SlGoto.setValue(
                    self._SlGoto.value() - self._SigSlStep.value())

            # ------------ AMPLITUDE ------------
            elif event.text in ['-', '+']:  # Decrease / increase amplitude
                delta = 2.5
                sign = 2 * ['-', '+'].index(event.text) - 1
                if self._PanAmpSym.isChecked():  # Symetric amplitudes :
                    val_sym = self._PanAllAmpMax.value() - 2 * sign * delta
                    self._PanAllAmpMax.setValue(val_sym)
                else:  # non-symetrical amplitudes
                    for mi, ma in zip(self._yminSpin, self._ymaxSpin):
                        mi.setValue(mi.value() + sign * delta)
                        ma.setValue(ma.value() - sign * delta)

            # ------------  GRID/MAGNIFY ------------
            elif event.text.lower() == 'm':  # Magnify
                viz = self._slMagnify.isChecked()
                self._slMagnify.setChecked(not viz)
                self._fcn_slider_magnify()

            elif event.text.lower() == 'g':  # Grid
                viz = self._slGrid.isChecked()
                self._slGrid.setChecked(not viz)
                self._fcn_grid_toggle()

            # ------------ SCORING ------------
            elif event.text.lower() == 'a':  # Art
                self._add_stage_on_scorwin(-1)
                self._SlGoto.setValue(self._SlGoto.value(
                ) + self._SigSlStep.value())
                logger.info("Art stage inserted")
            elif event.text.lower() == 'w':  # Wake
                self._add_stage_on_scorwin(0)
                self._SlGoto.setValue(self._SlGoto.value(
                ) + self._SigSlStep.value())
                logger.info("Wake stage inserted")
            elif event.text == '1':
                self._add_stage_on_scorwin(1)
                self._SlGoto.setValue(self._SlGoto.value(
                ) + self._SigSlStep.value())
                logger.info("N1 stage inserted")
            elif event.text == '2':
                self._add_stage_on_scorwin(2)
                self._SlGoto.setValue(self._SlGoto.value(
                ) + self._SigSlStep.value())
                logger.info("N2 stage inserted")
            elif event.text == '3':
                self._add_stage_on_scorwin(3)
                self._SlGoto.setValue(self._SlGoto.value(
                ) + self._SigSlStep.value())
                logger.info("N3 stage inserted")
            elif event.text.lower() == 'r':
                self._add_stage_on_scorwin(4)
                self._SlGoto.setValue(self._SlGoto.value(
                ) + self._SigSlStep.value())
                logger.info("REM stage inserted")
        #    wy 删除快捷键
            elif event.text.lower() == 'd':
                self._fcn_rm_selected_event()

        @canvas.events.mouse_release.connect
        def on_mouse_release(event):
            """Executed function when the mouse is pressed over canvas.

            This method set the transformation to the canvas to NullTransform.
            """
            # Get canvas name :
            name = canvas.title
            condition = bool(name.find('Canvas') + 1)
            if condition and not self._slMagnify.isChecked():
                # Get channel name :
                chan = name.split('Canvas_')[1]
                # Get index :
                idx = self._channels.index(chan)
                # Build transformation :
                self._chan.node[idx].transform = vist.NullTransform()

        @canvas.events.mouse_double_click.connect
        # wy
        def on_mouse_double_click(event):
            """Executed function when double click mouse over canvas.

            :event: the trigger event
            """
            # Get canvas title :
            is_sp_hyp = canvas.title in ['Hypnogram', 'Spectrogram']
            title = canvas.title if is_sp_hyp else canvas.title.split('_')[1]
            # Annotate the timing :
            if is_sp_hyp:
                # wypos
                event.pos[0] = event.pos[0] - 50
                y = canvas.size[0] - 50
                # cursor = self._time[-1] * event.pos[0] / canvas.size[0]
                cursor = self._time[-1] * event.pos[0] / y
            else:
                # 标尺数据（第几个30秒？）
                val = self._SlVal.value()
                # 步长数据
                step = self._SigSlStep.value()
                # 窗口数据
                win = self._SigWin.value()
                # tm：最左边，th：最右边
                tm, th = (val * step, val * step + win)
                # wypos
                event.pos[0] = event.pos[0] - 50
                y = canvas.size[0] - 50
                # cursor = tm + ((th - tm) * event.pos[0] / canvas.size[0])
                cursor = tm + ((th - tm) * event.pos[0] / y)
            ## //wy 设置当前页面为检测页面
            self.QuickSettings.setCurrentIndex(4)
            chan, types = self._get_current_chan_type()
            # index = self._detect[(chan, types)]['index']
            # 升到采样率倍，并取整
            x = np.round(cursor * self._sf)
            y = int(np.round(cursor * self._sf))
            start = int(np.floor(cursor * self._sf))
            # start_fix = start-110
            index = self._detect[(chan, types)]['index']
            # 如果是伪迹数据
            if (index.shape[1] == 5):
                self._detect[(chan, types)]['index'] = np.append(self._detect[(chan, types)]['index'],[[start, start+1, -1, -1, -1]], axis=0)

            else:
                self._detect[(chan, types)]['index'] = np.append(self._detect[(chan, types)]['index'], [[start, start+1]], axis=0)
            self._loc_line_report_add(refresh=False)
            # 光标指到最后一行
            self._DetectLocations.selectRow(self._DetectLocations.rowCount() - 1)
            ## wy//
            # Set the current tab to the annotation tab :
            # self.QuickSettings.setCurrentIndex(5)
            # Run annotation :
            # self._fcn_annotate_add('', (cursor, cursor), title)

        @canvas.events.mouse_move.connect
        def on_mouse_move(event):
            """Executed function when the mouse move over canvas.

            Magnify for all channels under cursor locations.
            """
            # Get mouse cursor position for the specified canvas :
            zoom = self.menuDispZoom.isChecked()
            if canvas.title in ['Hypnogram', 'Spectrogram'] and not zoom:
                # wypos
                event.pos[0] = event.pos[0] - 50
                y = canvas.size[0] - 50
                # cursor = self._time[-1] * event.pos[0] / canvas.size[0]
                cursor = self._time[-1] * event.pos[0] / y
            else:
                # Get time parameters (window, step, slider value) :
                val = self._SlVal.value()
                step = self._SigSlStep.value()
                win = self._SigWin.value()
                tm, th = (val * step, val * step + win)
                # Convert cursor in time position :
                # wypos
                event.pos[0] = event.pos[0] - 50
                y = canvas.size[0] - 50
                # cursor = tm + ((th - tm) * event.pos[0] / canvas.size[0])
                cursor = tm + ((th - tm) * event.pos[0] / y)
                # Enable/Disable magnify :
                if self._slMagnify.isChecked():
                    for i, k in self._chan:
                        self._chan.node[i].transform.center = (cursor, 0.)
                        k.update()
                    tm, th = self._time.min(), self._time.max()
            # Set time position to the cursor text :
            cursor = np.round(cursor * 1000.) / 1000.
            self._txtCursor.setText('Cursor : ' + str(cursor) + ' sec')

        @canvas.events.mouse_press.connect
        def on_mouse_press(event):
            """Executed function when single click mouse over canvas.

            Magnigy the signal under the mouse cursor only.
            """
            # ------------- MAGNIFY : CTRL + left click -------------
            name = canvas.title
            # print(self._is_right_click(event))
            is_left = self._is_left_click(event)
            is_ctrl = self._is_modifier(event, 'Control')
            # wy
            is_alt = self._is_modifier(event, 'Alt')
            # 左键+alt键同时按下触发事件
            altCondition = bool(name.find('Canvas') + 1) and is_left and is_alt
            if altCondition and not self._slMagnify.isChecked():
                # Get channel name :
                chan = name.split('Canvas_')[1]
                # Get index :
                idx = self._channels.index(chan)
                # Get cursor position :
                val = self._SlVal.value()
                step = self._SigSlStep.value()
                win = self._SigWin.value()
                tm, th = (val * step, val * step + win)
                # wypos
                event.pos[0] = event.pos[0] - 50
                y = canvas.size[0] - 50
                # cursor = tm + ((th - tm) * event.pos[0] / canvas.size[0])
                cursor = tm + ((th - tm) * event.pos[0] / y)
                # Build transformation :
                self.QuickSettings.setCurrentIndex(4)
                chan, types = self._get_current_chan_type()
                # index = self._detect[(chan, types)]['index']
                # 升到采样率倍，并取整
                x = np.round(cursor * self._sf)
                y = int(np.round(cursor * self._sf))
                end = int(np.floor(cursor * self._sf))
                # start_fix = start-110
                # 末尾行的下标
                endIndex = self._detect[(chan, types)]['index'].shape[0] - 1

                test_start = self._detect[(chan, types)]['index'][endIndex][0]
                test_end = self._detect[(chan, types)]['index'][endIndex][1]
                dur = test_end - test_start
                # 判断最后一行相差是否是1，若是，末尾行第二个值修改为end
                if(dur == 1):
                    self._detect[(chan, types)]['index'][endIndex][1] = end

                # self._detect[(chan, types)]['index'] = np.append(self._detect[(chan, types)]['index'],
                #                                                  [[end, end + 1]], axis=0)

                # wy修复指针bug
                chan, types = self._get_current_chan_type()
                index = self._detect[(chan, types)]['index']
                # 如果是伪迹数据

                # wy 对start排序，若相同，对end排序，还相同，对次序排序
                # 按照排序键优先级从后先前，如keys为(x,y,z)，排序结果按照先按z排序，然后y，最后x。
                # 注意事项2：当输入的排序键为二维数组时按照行进行排序。排序键优先级依旧从后先前
                arrSortedIndex = np.lexsort((index[:, 1], index[:, 0]))
                index = index[arrSortedIndex, :]
                self._detect[(chan, types)]['index'] = index
                # index.lexsort
                # index.sort(axis=0)
                # 找到加入的end所在行
                currentRow = np.searchsorted(index[:,1],end)
                dur = (index[:, 1] - index[:, 0]) * (1000. / self._sf)
                self._detect.build_hyp(chan, types)
                self._fcn_fill_locations(chan, types, index, dur)
                # wy修复指针bug、
                self._loc_line_report_add(refresh=False)
                # 光标指到插入应有位置的下一行
                self._DetectLocations.selectRow(currentRow)

            condition = bool(name.find('Canvas') + 1) and is_left and is_ctrl
            if condition and not self._slMagnify.isChecked():
                # Get channel name :
                chan = name.split('Canvas_')[1]
                # Get index :
                idx = self._channels.index(chan)
                # Get cursor position :
                val = self._SlVal.value()
                step = self._SigSlStep.value()
                win = self._SigWin.value()

                tm, th = (val * step, val * step + win)
                # wypos
                event.pos[0] = event.pos[0] - 50
                y = canvas.size[0] - 50
                # cursor = tm + ((th - tm) * event.pos[0] / canvas.size[0])
                cursor = tm + ((th - tm) * event.pos[0] / y)
                # Build transformation :
                # kwargs = {'center': (cursor, 0.), 'radii': (3, 15), 'mag': 10}
                kwargs = {'center': (cursor, 0.), 'radii': (0.5, 3), 'mag': 3}
                transform = vist.nonlinear.Magnify1DTransform(**kwargs)
                # transform = vist.nonlinear.Magnify1DTransformY(**kwargs)
                self._chan.node[idx].transform = transform
                # wy 放大添加两条竖线
                ix = self._channels.index(chan)
                self._chan.set_location(self._sf, self._data[ix,:], ix, cursor-0.5, cursor+0.5)


            # 鼠标左键



        @canvas.events.mouse_wheel.connect
        def on_mouse_wheel(event):
            pass




class Visuals(CanvasShortcuts):
    """Create the visual objects to be added to the scene."""

    def __init__(self):
        """Init."""
        # =================== VARIABLES ===================
        sf, data, time = self._sf, self._data, self._time
        channels, hypno, cameras = self._channels, self._hypno, self._allCams
        # wy第二睡眠标签
        if self._hypno2Flag:
            hypno2_flag = True
            hypno_2 = self._hypno2
        else:
            hypno2_flag = False
        # =================== CHANNELS ===================
        self._chan = ChannelPlot(channels, time, camera=cameras[0],
                                 color=self._chancolor, width=self._lw,
                                 color_detection=self._indicol,
                                 parent=self._chanCanvas,
                                 fcn=self._fcn_slider_move)
        PROFILER('Channels', level=1)

        # =================== SPECTROGRAM ===================
        # Create a spectrogram object :
        self._spec = Spectrogram(camera=cameras[1],
                                 fcn=self._fcn_spec_set_data,
                                 parent=self._specCanvas.wc.scene)
        self._spec.set_data(sf, data[0, ...], time, cmap=self._defcmap)
        PROFILER('Spectrogram', level=1)
        # Create a visual indicator for spectrogram :
        self._specInd = Indicator(name='spectro_indic', visible=True, alpha=.3,
                                  parent=self._specCanvas.wc.scene)
        self._specInd.set_data(xlim=(0, 30), ylim=(0, 20))
        PROFILER('Spectrogram indicator', level=1)

        # =================== HYPNOGRAM ===================
        # Create a hypnogram object :
        self._hyp = Hypnogram(time, camera=cameras[2], color=self._hypcolor,
                              width=self._lwhyp, hconv=self._hconv,
                              parent=self._hypCanvas.wc.scene)
        # wy 第二睡眠标签
        if hypno2_flag:
            # wy 第二睡眠标签
            self._hyp.set_data2(sf, hypno, hypno_2, time)

        else:
            self._hyp.set_data(sf, hypno, time)
        PROFILER('Hypnogram', level=1)
        # Create a visual indicator for hypnogram :
        self._hypInd = Indicator(name='hypno_indic', visible=True, alpha=.3,
                                 parent=self._hypCanvas.wc.scene)
        self._hypInd.set_data(xlim=(0., 30.), ylim=(-6., 2.))
        PROFILER('Hypnogram indicator', level=1)
        # wy 颜色
        # =================== DETECTIONS ===================
        self._detect = Detection(self._channels.copy(), self._time,
                                 self._defspin, self._defrem, self._defkc,
                                 self._defsw, self._defpeaks, self._defmt,self._defspina,self._defspinb,
                                 self._spinsym, self._remsym, self._kcsym,
                                 self._swsym, self._peaksym, self._mtsym,
                                 self._chan.node, self._hypCanvas.wc.scene)
        PROFILER('Detections', level=1)

        # =================== TOPOPLOT ===================
        self._topo = TopoSleep(channels=self._channels, margin=.2,
                               parent=self._topoCanvas.wc.scene)
        # Set camera properties :
        cameras[3].rect = self._topo.rect
        cameras[3].aspect = 1.
        self._pan_pick.model().item(3).setEnabled(any(self._topo._keeponly))
        PROFILER('Topoplot', level=1)

        # =================== SHORTCUTS ===================
        vbcanvas = self._chanCanvas + [self._specCanvas, self._hypCanvas]
        for k in vbcanvas:
            CanvasShortcuts.__init__(self, k.canvas)
        self._shpopup.set_shortcuts(self.sh)
        PROFILER('Shortcuts', level=1)
