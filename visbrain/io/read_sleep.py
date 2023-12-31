"""Load sleep files.

This file contain functions to load :
- European Data Format (*.edf)
- Micromed (*.trc)
- BrainVision (*.vhdr)
- ELAN (*.eeg)
- Hypnogram (*.hyp)
"""
import os
import io
from warnings import warn
import logging
import datetime
import neurokit2 as nk

import numpy as np
from scipy.stats import iqr

from visbrain.io.dependencies import is_mne_installed
from visbrain.io.dialog import dialog_load
from visbrain.io.mneio import mne_switch
from visbrain.io.rw_hypno import (read_hypno, oversample_hypno, read_coefficient)
from visbrain.io.rw_utils import get_file_ext
from visbrain.io.write_data import write_csv
from visbrain.io import merge_annotations

from visbrain.utils.others import get_dsf
from visbrain.utils.mesh import vispy_array
from visbrain.utils.sleep.hypnoprocessing import sleepstats
from visbrain.utils.sleep.detection import filt_data

from visbrain.config import PROFILER

logger = logging.getLogger('visbrain')

__all__ = ['ReadSleepData', 'get_sleep_stats']


class ReadSleepData(object):
    """Main class for reading sleep data."""
    # wy第二睡眠标签
    def __init__(self, data, channels, sf, hypno, hypno_2, hypno_2_flag, href, preload, use_mne,
                 downsample, kwargs_mne, annotations):
        """Init."""
        # ========================== LOAD DATA ==========================
        # Dialog window if data is None :
        if data is None:
            data = dialog_load(self, "Open dataset", '',
                               "Any EEG files (*.vhdr *.edf *.gdf *.bdf *.eeg *.mat "
                               "*.egi *.mff *.cnt *.trc *.set *.rec);;"
                               "BrainVision (*.vhdr);;EDF (*.edf);;"
                               "GDF (*.gdf);;BDF (*.bdf);;Elan (*.eeg);;"
                               "EGI (*.egi);;MFF (*.mff);;CNT (*.cnt);;"
                               "Micromed (*.trc);;EEGLab (*.set);;REC (*.rec)")
            # 仅用于读取睡眠阶段
            upath = os.path.split(data)[0]
        else:
            upath = ''

        if isinstance(data, str):  # file is defined
            # ---------- USE SLEEP or MNE ----------
            # Find file extension :
            file, ext = get_file_ext(data)
            # Force to use MNE if preload is False :
            use_mne = True if not preload else use_mne
            # Get if the file has to be loaded using Sleep or MNE python :
            sleep_ext = ['.eeg', '.vhdr', '.edf', '.trc', '.rec', '.mat']
            use_mne = True if ext not in sleep_ext else use_mne

            if use_mne:
                is_mne_installed(raise_error=True)

            # ---------- LOAD THE FILE ----------
            if use_mne:  # Load using MNE functions
                logger.debug("Load file using MNE-python")
                kwargs_mne['preload'] = preload
                args = mne_switch(file, ext, downsample, **kwargs_mne)
            else:  # Load using Sleep functions
                logger.debug("Load file using Sleep")
                args = sleep_switch(file, ext, downsample)
            # Get output arguments :
            (sf, downsample, dsf, data, channels, n, offset, annot) = args
            info = ("Data successfully loaded (%s):"
                    "\n- Sampling-frequency : %.2fHz"
                    "\n- Number of time points (before down-sampling): %i"
                    "\n- Down-sampling frequency : %.2fHz"
                    "\n- Number of time points (after down-sampling): %i"
                    "\n- Number of channels : %i"
                    )
            n_channels, n_pts_after = data.shape
            logger.info(info % (file + ext, sf, n, downsample, n_pts_after,
                                n_channels))
            PROFILER("Data file loaded", level=1)

        elif isinstance(data, np.ndarray):  # array of data is defined
            if not isinstance(sf, (int, float)):
                raise ValueError("When passing raw data, the sampling "
                                 "frequency parameter, sf, must either be an "
                                 "integer or a float.")
            file = annot = None
            offset = datetime.time(0, 0, 0)
            dsf, downsample = get_dsf(downsample, sf)
            n = data.shape[1]
            # # wy置信度对应通道滤波 + 转换对侧参考
            # data[[14],:] = data[[14],:] + data[[12],:]
            # data[[16],:] = data[[16],:] - data[[12],:]
            # data[[15, 13, 14, 16], :] = filt_data(data[[15, 13, 14, 16], :], 0.5, 35, sf, order=7)
            # data[[8], :] = filt_data(data[[8], :], 10, 100, sf, order=7)
            # data[[9], :] = filt_data(data[[9], :], 0.3, 70, sf, order=7)
            # # wy心电 使用nk算法预处理
            # ecg_signal       = nk.signal_sanitize(data[[10], :])
            # data[[10], :]    = nk.ecg_clean(ecg_signal, sampling_rate=sf)
            # data = filt_data(data,49.5,50.5,sf,order=7)
            # # 降采样，每间隔dsf个点取一个点
            # data = data[:, ::dsf]
        else:
            raise IOError("The data should either be a string which refer to "
                          "the path of a file or an array of raw data of shape"
                          " (n_electrodes, n_time_points).")

        # Keep variables :
        self._file = file
        # wy
        self._ext = ext
        self._annot_file = np.c_[merge_annotations(annotations, annot)]
        self._N = n
        self._dsf = dsf 
        self._sfori = float(sf)
        self._toffset = offset.hour * 3600. + offset.minute * 60. + \
            offset.second
        # 降采样后的时间点（秒数）
        time = np.arange(n)[::dsf] / sf
        self._sf = float(downsample) if downsample is not None else float(sf)

        # ========================== LOAD HYPNOGRAM ==========================
        # Dialog window for hypnogram :
        if hypno is None:
            hypno = dialog_load(self, "Open hypnogram", upath,
                                "Text file (*.txt);;Elan (*.hyp);;"
                                "CSV file (*.csv);;EDF+ file(*.edf);"
                                ";All files (*.*)")
            hypno = None if hypno == '' else hypno


        if isinstance(hypno, np.ndarray):  # array_like
            if len(hypno) == n:
                hypno = hypno[::dsf]
            else:
                raise ValueError("Then length of the hypnogram must be the "
                                 "same as raw data")
        if isinstance(hypno, str):  # (*.hyp / *.txt / *.csv)
            # coefficient = hypno
            coefficient_path = os.path.splitext(hypno)[0] + '_coefficient.txt'
            hypno, _ = read_hypno(hypno, time=time, datafile=file)
            # Oversample then downsample :
            hypno = oversample_hypno(hypno, self._N)[::dsf]
            # wy置信度
            wy_N = self._N / 10;
            # 如果有置信度文件,再处理data与channels
            if os.path.isfile(coefficient_path):
                coefficient = read_coefficient(coefficient_path, self._N, time=time, datafile=file, )[::dsf]
                data = np.row_stack((data, coefficient))
                channels.append('Coefficient')
                # channels = ['EOG Left', 'EOG Right', 'C3-A1', 'O2-A2', 'EMG', 'ECG IIHF', 'ECG II', 'Coefficient',
                #             'Effort Tho',
                #             'Effort Abd', 'Snore', 'SpO2', 'Flow Patient-0', 'Flow Patient-1', 'Pulse', 'Event', 'Body',
                #             'A1-A2',
                #             'PPG']
                n_channels = n_channels + 1;
            # 如果没有置信度文件
            # else:
            #     # data = np.row_stack((data, coefficient))
            #     data = data[[15, 13, 14, 16, 8, 9, 10, 18, 0, 1, 2, 3, 4, 5, 6, 7, 11, 12, 17], :]
            # coefficient = oversample_hypno(coefficient, self._N)[::dsf] / dsf
            # coefficient = oversample_hypno(coefficient, wy_N)
            # # 对应通道滤波
            # data[[0,1,2,3],:] = filt_data(data[[0,1,2,3],:],0.5,35,100,order=7)
            # data[[4],:] = filt_data(data[[4],:],10,99,100,order=7)
            # data[[5,6],:] = filt_data(data[[5,6],:],0.3,70,100,order=7)
            PROFILER("Hypnogram file loaded", level=1)

        #     wy--读第二睡眠标签
        # if hypno_2 is None:
        #     hypno_2 = dialog_load(self, "Open hypnogram_2", upath,
        #                           "Text file (*.txt);;Elan (*.hyp);;"
        #                           "CSV file (*.csv);;EDF+ file(*.edf);"
        #                           ";All files (*.*)")
        #     hypno_2 = None if hypno_2 == '' else hypno_2
        #
        # if isinstance(hypno_2, np.ndarray):  # array_like
        #     if len(hypno_2) == n:
        #         hypno_2 = hypno_2[::dsf]
        #     else:
        #         raise ValueError("Then length of the hypnogram_2 must be the "
        #                          "same as raw data")
        #
        # if isinstance(hypno_2, str):  # (*.hyp / *.txt / *.csv)
        #     hypno_2, _ = read_hypno(hypno_2, time=time, datafile=file)
        #     # Oversample then downsample :
        #     hypno_2 = oversample_hypno(hypno_2, self._N)[::dsf]
        #     PROFILER("Hypnogram_2 file loaded", level=1)



        # ========================== CHECKING ==========================
        # ---------- DATA ----------
        # Check data shape :
        if data.ndim != 2:
            raise ValueError("The data must be a 2D array")
        nchan, npts = data.shape

        # ---------- CHANNELS ----------
        if (channels is None) or (len(channels) != nchan):
            warn("The number of channels must be " + str(nchan) + ". Default "
                 "channel names will be used instead.")
            channels = ['chan' + str(k) for k in range(nchan)]

        # ---------- STAGE ORDER ----------
        # href checking :
        absref = ['art', 'wake', 'n1', 'n2', 'n3', 'rem']
        absint = [-1, 0, 1, 2, 3, 4]
        if href is None:
            href = absref
        elif (href is not None) and isinstance(href, list):
            # Force lower case :
            href = [k.lower() for k in href]
            # Check that all stage are present :
            for k in absref:
                if k not in href:
                    raise ValueError(k + " not found in href.")
            # Force capitalize :
            href = [k.capitalize() for k in href]
            href[href.index('Rem')] = 'REM'
        else:
            raise ValueError("The href parameter must be a list of string and"
                             " must contain 'art', 'wake', 'n1', 'n2', 'n3' "
                             "and 'rem'")
        # Conversion variable :
        absref = ['Art', 'Wake', 'N1', 'N2', 'N3', 'REM']
        conv = {absint[absref.index(k)]: absint[i] for i, k in enumerate(href)}

        # ---------- HYPNOGRAM ----------
        if hypno is None:
            hypno = np.zeros((npts,), dtype=np.float32)
        else:
            n = len(hypno)
            # Check hypno values :
            # 阶段不符合要求的话全置零
            if (hypno.min() < -1.) or (hypno.max() > 4) or (n != npts):
                warn("\nHypnogram values must be comprised between -1 and 4 "
                     "(see Iber et al. 2007). Use:\n-1 -> Art (optional)\n 0 "
                     "-> Wake\n 1 -> N1\n 2 -> N2\n 3 -> N4\n 4 -> REM\nEmpty "
                     "hypnogram will be used instead")
                hypno = np.zeros((npts,), dtype=np.float32)

        # ---------- SCALING ----------
        # Assume that the inter-quartile amplitude of EEG data is ~50 uV

        iqr_chan = iqr(data[:, :int(data.shape[1] / 4)], axis=-1)
        bad_iqr = iqr_chan < 1.

        if np.any(bad_iqr):
            mult_fact = np.zeros_like(iqr_chan)
            iqr_chan[iqr_chan == 0.] = 1.
            mult_fact[bad_iqr] = np.floor(np.log10(50. / iqr_chan[bad_iqr]))
            # wy置信度-第八通道 不需要缩放
            mult_fact[7] = 0
            # wy伪迹置信度 更新缩放因子，这段代码被注释了
            # data *= 10. ** mult_fact[..., np.newaxis]
            # /wy伪迹置信度 更新缩放因子
            # data[[7],:] = data[[7],:] / 10. ** mult_fact[..., np.newaxis]
            # data[[0,1, 2, 3, 4, 5, 6, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19], :] =data[[0,1, 2, 3, 4, 5, 6, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19], :] * 10. ** mult_fact[..., np.newaxis]
            warn("Wrong channel data amplitude. ")
            # data[[15, 13, 14, 16, 8, 9, 10, 18, 0, 1, 2, 3, 4, 5, 6, 7, 11, 12, 17], :]
        # ---------- CONVERSION ----------=
        # Convert data and hypno to be contiguous and float 32 (for vispy):
        self._data = vispy_array(data)
        self._hypno = vispy_array(hypno)
        # wy 睡眠第二标签
        if hypno_2 is not None:
            self._hypno2Flag = True
            self._hypno2 = vispy_array(hypno_2)
        else:
            self._hypno2Flag = False
            self._hypno2 = None
        self._time = vispy_array(time)
        self._channels = channels
        self._href = href
        self._hconv = conv
        PROFILER("Check data", level=1)

# 选不同方法读不同格式文件
def sleep_switch(file, ext, downsample):
    """Switch between sleep data files.

    Parameters
    ----------
    file : string
        Path to the file to load.
    ext : string
        Extension name (e.g. '.eeg')
    downsample : int
        Down-sampling frequency.

    Returns
    -------
    sf : float
        The original sampling-frequency.
    downsample : float
        The down-sampling frequency used.
    dsf : int
        The down-sampling factor.
    data : array_like
        The raw data of shape (n_channels, n_points)
    channels : list
        List of channel names.
    n : int
        Number of time points before down-sampling.
    start_time : datetime.time
        The time offset.
    annotations : array_like
        Array of annotations.
    """
    # Get full path :
    path = file + ext

    if ext == '.vhdr':  # BrainVision
        return read_bva(path, downsample)

    if ext == '.eeg':  # Elan
        return read_elan(path, downsample)

    if ext == '.mat':  # Elan
        return read_mat(path, downsample)

    elif ext in ['.edf', '.rec']:  # European Data Format
        return read_edf(path, downsample)

    elif ext == '.trc':  # Micromed
        return read_trc(path, downsample)

    else:  # None
        raise ValueError("*" + ext + " files are currently not supported.")


###############################################################################
###############################################################################
#                               LOAD FILES
###############################################################################
###############################################################################

def read_edf(path, downsample):
    """Read data from a European Data Format (edf) file.

    Use phypno class for reading EDF files:
        http: // phypno.readthedocs.io / api / phypno.ioeeg.edf.html

    Parameters
    ----------
    path: str
        Filename(with full path) to EDF file
    downsample : int
        Down-sampling frequency.

    Returns
    -------
    sf : int
        The sampling frequency.
    data : array_like
        The data organised as well(n_channels, n_points)
    chan : list
        The list of channel's names.
    n : int
        Number of points in the original data
    start_time : array_like
        Starting time of the recording (hh:mm:ss)
    annotations : array_like
        Array of annotations.
    """
    assert os.path.isfile(path)

    from ..utils.sleep.edf import Edf

    edf = Edf(path)

    # Return header informations
    _, start_time, sf, chan, n_samples, _ = edf.return_hdr()
    start_time = start_time.time()

    # Keep only data channels (e.g excludes marker chan)
    freqs = np.unique(edf.hdr['n_samples_per_record']) / edf.hdr[
        'record_length']
    sf = freqs.max()

    if len(freqs) != 1:
        bad_chans = np.where(edf.hdr['n_samples_per_record'] < sf)
        chan = np.delete(chan, bad_chans)

    # Load all samples of selected channels
    np.seterr(divide='ignore', invalid='ignore')
    data = edf.return_dat(chan, 0, n_samples)

    # Get original signal length :
    n = data.shape[1]

    # Get down-sample factor :
    sf = float(sf)
    chan = list(chan)
    dsf, downsample = get_dsf(downsample, sf)

    return sf, downsample, dsf, data[:, ::dsf], chan, n, start_time, None

# wy读取mat文件，根据数据集修改
def read_mat(path, downsample):
    assert os.path.isfile(path)
    from scipy.io import loadmat
    # 用h5py读7.3+版本， scipy.io旧
    import h5py
    data = h5py.File(os.path.join(path), 'r')
    # mat = loadmat(os.path.join(path))
    # wy 可修改
    # data = mat['eegdata']
    data = data['data'];
    data = np.asarray(data);
    data = data.T;
    # 数据点的数量
    n = data.shape[1]
    start_time = datetime.time(7, 48, 37)
    # 采样率
    # sf = float(256)
    # sf = float(100)
    # # chan = ['F3','F4','C3','C4','O1','O2','ECG','Euc','Manh','Mink']
    # chan = ['FP1', 'FP2', 'C3', 'C4', 'O1', 'O2', 'T3','T4','EOG1','EOG2','EMG','ECG1','ECG2','ECG3', 'Euc', 'Manh', 'Mink']

    if len(data) == 17:
        sf = float(100)
        chan = ['FP1', 'FP2', 'C3', 'C4', 'O1', 'O2', 'T3', 'T4', 'EOG1', 'EOG2', 'EMG', 'ECG1', 'ECG2', 'ECG3', 'Euc',
                'Manh', 'Mink']
    else:
        sf = float(1000)
        chan = ['FP1', 'FP2', 'F3', 'F4', 'C3', 'C4', 'O1', 'O2', 'P3', 'X2', 'X3', 'EOG1', 'EOG2', 'EMG', 'ECG',
                'Euc', 'Manh', 'Mink']


    dsf, downsample = get_dsf(downsample, sf)


    return sf, downsample, dsf, data[:, ::dsf], chan, n, start_time, None


def read_trc(path, downsample):
    """Read data from a Micromed (trc) file (version 4).

    Poor man's version of micromedio.py from Neo package
    (https://pythonhosted.org/neo/)

    Parameters
    ----------
    path : str
        Filename(with full path) to .trc file
    downsample : int
        Down-sampling frequency.

    Returns
    -------
    sf : float
        The sampling frequency.
    downsample : float
        The downsampling frequency
    data : array_like
        The data organised as well(n_channels, n_points)
    chan : list
        The list of channel's names.
    n : int
        Number of samples before down-sampling.
    start_time : array_like
        Starting time of the recording (hh:mm:ss)
    annotations : array_like
        Array of annotations.
    """
    import struct

    def read_f(f, fmt):
        return struct.unpack(fmt, f.read(struct.calcsize(fmt)))

    with io.open(path, 'rb') as f:
        # Read header
        f.seek(175, 0)
        header_version, = read_f(f, 'b')
        assert header_version == 4

        f.seek(138, 0)
        data_start_offset, n_chan, _, sf, nbytes = read_f(f, 'IHHHH')

        f.seek(128, 0)
        day, month, year, hour, minute, sec = read_f(f, 'bbbbbb')
        start_time = datetime.time(hour, minute, sec)

        # Raw data
        f.seek(data_start_offset, 0)
        m_raw = np.fromstring(f.read(), dtype='u' + str(nbytes))
        m_raw = m_raw.reshape((int(m_raw.size / n_chan), n_chan)).transpose()

        # Read label / gain
        gain = []
        chan = []
        logical_ground = []
        data = np.empty(shape=m_raw.shape, dtype=np.float32)

        f.seek(176, 0)
        zone_names = ['ORDER', 'LABCOD']
        zones = {}
        for zname in zone_names:
            zname2, pos, length = read_f(f, '8sII')
            zones[zname] = zname2, pos, length

        zname2, pos, length = zones['ORDER']
        f.seek(pos, 0)
        code = np.fromfile(f, dtype='u2', count=n_chan)

        for c in range(n_chan):
            zname2, pos, length = zones['LABCOD']
            f.seek(pos + code[c] * 128 + 2, 0)

            chan = np.append(chan, f.read(6).decode('utf-8').strip())
            logical_min, logical_max, logic_ground_chan, physical_min, \
                physical_max = read_f(f, 'iiiii')

            logical_ground = np.append(logical_ground, logic_ground_chan)

            gain = np.append(gain, float(physical_max - physical_min) /
                             float(logical_max - logical_min + 1))

    # Multiply by gain
    m_raw = m_raw - logical_ground[:, np.newaxis]
    data = m_raw * gain[:, np.newaxis].astype(np.float32)

    # Get original signal length :
    n = data.shape[1]

    # Get down-sample factor :
    sf = float(sf)
    chan = list(chan)
    dsf, downsample = get_dsf(downsample, sf)

    return sf, downsample, dsf, data[:, ::dsf], chan, n, start_time, None


def read_bva(path, downsample, read_markers=False):
    """Read data from a BrainVision (*.vhdr) file.

    Poor man's version of https: // gist.github.com / breuderink / 6266871

    Assumes that data are saved with the following parameters:
        - Data format: Binary
        - Orientation: Multiplexed
        - Format: int16

    Parameters
    ----------
    path : str
        Filename(with full path) to .vhdr file. Data file must be in the
        same directory.
    downsample : int
        Down-sampling frequency.
    read_markers : bool | False
        Import markers from the .vmrk files as annotations

    Returns
    -------
    sf : float
        The sampling frequency.
    data : array_like
        The data organised as well(n_channels, n_points)
    chan : list
        The list of channel's names.
    n : int
        Number of points before down-sampling.
    start_time : array_like
        Starting time of the recording (hh:mm:ss)
    annotations : array_like
        Array of annotations.
    """
    import re

    assert os.path.isfile(path)

    # Read header
    ent = np.genfromtxt(path, delimiter='\n', usecols=[0],
                        dtype=None, skip_header=0, encoding='utf-8')

    for item in ent:
        if 'DataFile=' in item:
            data_file = item.split('=')[1]
            data_path = os.path.join(os.path.dirname(path), data_file)
            assert os.path.isfile(data_path)
        elif 'MarkerFile=' in item:
            marker_file = item.split('=')[1]
            marker_path = os.path.join(os.path.dirname(path), marker_file)
        elif 'NumberOfChannels=' in item:
            n_chan = int(re.findall('\d+', item)[0])
        elif 'SamplingInterval=' in item:
            si = float(re.findall("[-+]?\d*\.\d+|\d+", item)[0])
            sf = 1 / (si * 0.000001)
        elif 'DataFormat' in item:
            data_format = item.split('=')[1]
        elif 'BinaryFormat' in item:
            binary_format = item.split('=')[1]
        elif 'DataOrientation' in item:
            data_orient = item.split('=')[1]

    # Check binary format
    assert "BINARY" in data_format
    assert "INT_16" in binary_format
    assert "MULTIPLEXED" in data_orient

    # Extract channel labels and resolution
    start_label = np.array(np.where(np.char.find(ent, 'Ch1=') == 0)).min()
    chan = {}
    resolution = np.empty(shape=n_chan)

    for i, j in enumerate(range(start_label, start_label + n_chan)):
        chan[i] = re.split('\W+', ent[j])[1]
        resolution[i] = float(ent[j].split(",")[2])

    chan = np.array(list(chan.values())).flatten()

    # Read marker file (if present) to extract recording time
    if os.path.isfile(marker_path):
        vmrk = np.genfromtxt(marker_path, delimiter='\n', usecols=[0],
                             dtype=None, skip_header=0, encoding='utf-8')

        # Read start-time
        for item in vmrk:
            if 'New Segment' in item:
                st = re.split('\W+', item)[-1]
                start_time = datetime.time(int(st[8:10]), int(st[10:12]),
                                           int(st[12:14]))
                break
            else:
                start_time = datetime.time(0, 0, 0)

        # Read markers
        if read_markers:
            onsets = np.array([], dtype=float)
            durations = np.array([], dtype=float)
            descriptions = np.array([], dtype=str)
            for item in vmrk:
                if 'Mk' in item and ';' not in item:
                    onsets = np.append(onsets, int(
                        re.sub(r'\s', '', item).split(',')[2]))
                    durations = np.append(durations, int(
                        re.sub(r'\s', '', item).split(',')[3]))
                    descriptions = np.append(descriptions, re.sub(
                        r'\s', '', item).split(',')[1])
                    anot = np.c_[onsets, durations, descriptions]
        else:
            anot = None

    with io.open(data_path, 'rb') as f:
        raw = f.read()
        size = int(len(raw) / 2)

        ints = np.ndarray((n_chan, int(size / n_chan)),
                          dtype='<i2', order='F', buffer=raw)

        data = np.float32(np.diag(resolution)).dot(ints)

    # Get original signal length :
    n = data.shape[1]

    # Get down-sample factor :
    sf = float(sf)
    chan = list(chan)
    dsf, downsample = get_dsf(downsample, sf)

    return sf, downsample, dsf, data[:, ::dsf], chan, n, start_time, anot


def read_elan(path, downsample):
    """Read data from a ELAN (eeg) file.

    Elan format specs: http: // elan.lyon.inserm.fr/

    Parameters
    ----------
    path : str
        Filename(with full path) to Elan .eeg file
    downsample : int
        Down-sampling frequency.

    Returns
    -------
    sf : int
        The sampling frequency.
    data : array_like
        The data organised as well(n_channels, n_points)
    chan : list
        The list of channel's names.
    n : int
        Number of samples before down-sampling.
    start_time : array_like
        Starting time of the recording (hh:mm:ss)
    annotations : array_like
        Array of annotations.
    """
    header = path + '.ent'

    assert os.path.isfile(path)
    assert os.path.isfile(header)

    # Read .ent file
    ent = np.genfromtxt(header, delimiter='\n', usecols=[0],
                        dtype=None, skip_header=0, encoding='utf-8')

    # eeg file version
    eeg_version = ent[0]

    if eeg_version == 'V2':
        nb_oct = 2
        formread = '>i2'
    elif eeg_version == 'V3':
        nb_oct = 4
        formread = '>i4'

    # Sampling rate
    sf = 1. / float(ent[8])

    # Record starting time
    if ent[4] != "No time":
        hour, minutes, sec = ent[4].split(':')
        start_time = datetime.time(int(hour), int(minutes), int(sec))
        day, month, year = ent[3].split(':')
    else:
        start_time = datetime.time(0, 0, 0)

    # Channels
    nb_chan = np.int(ent[9])
    nb_chan = nb_chan

    # Last 2 channels do not contain data
    nb_chan_data = nb_chan - 2
    chan_list = slice(nb_chan_data)
    chan = ent[10:10 + nb_chan_data]

    # Gain
    gain = np.zeros(nb_chan)
    offset1 = 9 + 3 * nb_chan
    offset2 = 9 + 4 * nb_chan
    offset3 = 9 + 5 * nb_chan
    offset4 = 9 + 6 * nb_chan

    for i in np.arange(1, nb_chan + 1):

        min_an = float(ent[offset1 + i])
        max_an = float(ent[offset2 + i])
        min_num = float(ent[offset3 + i])
        max_num = float(ent[offset4 + i])

        gain[i - 1] = (max_an - min_an) / (max_num - min_num)
    if gain.dtype != np.float32:
        gain = gain.astype(np.float32, copy=False)

    # Load memmap
    nb_bytes = os.path.getsize(path)
    nb_samples = int(nb_bytes / (nb_oct * nb_chan))

    m_raw = np.memmap(path, dtype=formread, mode='r',
                      shape=(nb_chan, nb_samples), order={'F'})

    # Get original signal length :
    n = m_raw.shape[1]

    # Get down-sample factor :
    sf = float(sf)
    chan = list(chan)
    dsf, downsample = get_dsf(downsample, sf)

    # Multiply by gain :
    data = m_raw[chan_list, ::dsf] * \
        gain[chan_list][..., np.newaxis]

    return sf, downsample, dsf, data, chan, n, start_time, None


def get_sleep_stats(hypno_file, output_file=None):
    """Compute sleep statistics from hypnogram file and export them in csv.

    Sleep statistics specifications:

        * Time in Bed (TIB) : total duration of the hypnogram.
        * Total Dark Time (TDT) : duration of the hypnogram from beginning
          to last period of sleep.
        * Sleep Period Time (SPT) : duration from first to last period of
          sleep.
        * Wake After Sleep Onset (WASO) : duration of wake periods within SPT
        * Sleep Efficiency (SE) : TST / TDT * 100 (%).
        * Total Sleep Time (TST) : SPT - WASO.
        * W, N1, N2, N3 and REM: sleep stages duration.
        * % (W, ... REM) : sleep stages duration expressed in percentages of
          TDT.
        * Latencies: latencies of sleep stages from the beginning of the
          record.

    (All values except SE and percentages are expressed in minutes)

    Parameters
    ----------
    hypno_file : string
        Full path to the hypnogram file.
    output_file : string | None
        Full path to the output file. If no file is provided, sleep statictics
        are print out to the terminal.
    """
    # File conversion :
    if output_file is not None:  # Check extension
        ext = os.path.splitext(output_file)[1][1:].strip().lower()
        if ext == '':
            output_file = output_file + '.csv'

    # Load hypnogram
    hypno, sf_hyp = read_hypno(hypno_file)
    if sf_hyp < 1:
        mult = int(np.round(len(hypno) / sf_hyp))
        hypno = oversample_hypno(hypno, mult)
        sf_hyp = 1

    # Get sleep stats
    stats = sleepstats(hypno, sf_hyp=sf_hyp)
    stats['File'] = hypno_file
    print('\nSLEEP STATS\n===========')
    keys, val = [''] * len(stats), [''] * len(stats)
    # Fill table :
    for num, (k, v) in enumerate(stats.items()):
        print(k, '\t', str(v))
        # Remember variables :
        keys[int(num)] = k
        val[int(num)] = str(v)
    if output_file is not None:
        write_csv(output_file, zip(keys, val))
        print('===========\nCSV file saved to:', output_file)
