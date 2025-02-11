import mmap
from pathlib import Path
from collections import OrderedDict

import numpy as np
import pytest

import astropy.io.fits as fits

import sunpy.data.test
import sunpy.io._fits
from sunpy.data.test import get_test_filepath, test_data_filenames
from sunpy.data.test.waveunit import MEDN_IMAGE, MQ_IMAGE, NA_IMAGE, SVSM_IMAGE
from sunpy.io._fits import extract_waveunit, get_header, header_to_fits
from sunpy.io.fits import extract_waveunit, format_comments_and_history, get_header, header_to_fits
from sunpy.util import MetaDict, SunpyMetadataWarning

TEST_RHESSI_IMAGE = get_test_filepath('hsi_image_20101016_191218.fits')
TEST_AIA_IMAGE = get_test_filepath('aia_171_level1.fits')
TEST_EIT_HEADER = get_test_filepath('EIT_header/efz20040301.000010_s.header')
TEST_SWAP_HEADER = get_test_filepath('SWAP/resampled1_swap.header')

# Some of the tests images contain an invalid BLANK keyword; ignore the warning
# raised by this
pytestmark = pytest.mark.filterwarnings("ignore:Invalid 'BLANK' keyword in header")


@pytest.mark.parametrize(
    'fname, hdus, length',
    [(TEST_RHESSI_IMAGE, None, 4),
     (TEST_RHESSI_IMAGE, 1, 1),
     (TEST_RHESSI_IMAGE, [1, 2], 2),
     (TEST_RHESSI_IMAGE, range(0, 2), 2)]
)
def test_read_hdus(fname, hdus, length):
    pairs = sunpy.io._fits.read(fname, hdus=hdus)
    assert len(pairs) == length


@pytest.mark.parametrize(
    'fname, waveunit',
    [(TEST_RHESSI_IMAGE, None),
     (TEST_EIT_HEADER, None),
     (TEST_AIA_IMAGE, 'angstrom'),
     (MEDN_IMAGE, 'nm'),
     (MQ_IMAGE, 'angstrom'),
     (NA_IMAGE, 'm'),
     (TEST_SWAP_HEADER, 'angstrom'),
     (SVSM_IMAGE, 'nm')]
)
def test_extract_waveunit(fname, waveunit):
    if Path(fname).suffix == '.header':
        header = format_comments_and_history(fits.Header.fromtextfile(fname))
    else:
        header = get_header(fname)[0]
    waveunit = extract_waveunit(header)
    assert waveunit is waveunit


def test_simple_write(tmpdir):
    data, header = sunpy.io._fits.read(TEST_AIA_IMAGE)[0]
    outfile = tmpdir / "test.fits"
    sunpy.io._fits.write(str(outfile), data, header)
    assert outfile.exists()


def test_extra_comment_write(tmpdir):
    data, header = sunpy.io._fits.read(TEST_AIA_IMAGE)[0]
    header["KEYCOMMENTS"]["TEST"] = "Hello world"
    outfile = tmpdir / "test.fits"
    sunpy.io._fits.write(str(outfile), data, header)
    assert outfile.exists()


def test_simple_write_compressed(tmpdir):
    data, header = sunpy.io._fits.read(TEST_AIA_IMAGE)[0]
    outfile = tmpdir / "test.fits"
    sunpy.io._fits.write(str(outfile), data, header, hdu_type=fits.CompImageHDU)
    assert outfile.exists()
    with fits.open(str(outfile)) as hdul:
        assert len(hdul) == 2
        assert isinstance(hdul[1], fits.CompImageHDU)


def test_simple_write_compressed_difftypeinst(tmpdir):
    # `hdu_type=fits.CompImageHDU` and `hdu_type=fits.CompImageHDU()`
    # should produce identical FITS files
    data, header = sunpy.io._fits.read(TEST_AIA_IMAGE)[0]
    outfile_type = str(tmpdir / "test_type.fits")
    outfile_inst = str(tmpdir / "test_inst.fits")
    sunpy.io._fits.write(outfile_type, data, header, hdu_type=fits.CompImageHDU)
    sunpy.io._fits.write(outfile_inst, data, header, hdu_type=fits.CompImageHDU())
    assert fits.FITSDiff(outfile_type, outfile_inst, ignore_comments=['PCOUNT']).identical


@pytest.mark.parametrize(
    'kwargs, should_fail',
    [({}, False),
     ({'quantize_level': -32}, True)]
)
def test_simple_write_compressed_instance(tmpdir, kwargs, should_fail):
    data, header = sunpy.io._fits.read(TEST_AIA_IMAGE)[0]
    outfile = tmpdir / "test.fits"

    # Ensure HDU instance is used correctly
    hdu = fits.CompImageHDU(data=np.array([0.]), **kwargs)
    hdu.header['HELLO'] = 'world'  # should be in the written file
    hdu.header['TELESCOP'] = 'other'  # should be replaced with 'SDO/AIA'
    hdu.header['NAXIS'] = 5  # should be replaced with 2
    sunpy.io._fits.write(str(outfile), data, header, hdu_type=hdu)
    assert outfile.exists()
    with fits.open(str(outfile)) as hdul:
        assert len(hdul) == 2
        assert isinstance(hdul[1], fits.CompImageHDU)
        assert hdul[1].header['HELLO'] == 'world'
        assert hdul[1].header['TELESCOP'] == 'SDO/AIA'
        assert hdul[1].header['NAXIS'] == 2
        data_preserved = hdul[1].data == pytest.approx(data, abs=10)
        print(np.abs(hdul[1].data - data).max())
        print(kwargs)
        if should_fail:  # high compression setting preserved
            assert not data_preserved
        else:
            assert data_preserved


def test_write_with_metadict_header_astropy(tmpdir):
    with fits.open(TEST_AIA_IMAGE) as fits_file:
        data, header = fits_file[0].data, fits_file[0].header
    meta_header = MetaDict(OrderedDict(header))
    temp_file = tmpdir / "temp.fits"
    with pytest.warns(SunpyMetadataWarning, match='The meta key comment is not valid ascii'):
        sunpy.io._fits.write(str(temp_file), data, meta_header)
    assert temp_file.exists()
    fits_file.close()

# Various warnings are thrown in this test, but we just want to check that the code
# works without exceptions


@pytest.mark.filterwarnings('ignore')
def test_fitsheader():
    """Test that all test data can be converted back to a FITS header."""
    extensions = ('.fts', '.fits')
    for ext in extensions:
        test_files = [f for f in test_data_filenames() if f.suffix == ext]
        for ffile in test_files:
            fits_file = fits.open(ffile)
            fits_file.verify("fix")
            meta_header = MetaDict(OrderedDict(fits_file[0].header))
            sunpy.io._fits.header_to_fits(meta_header)
            fits_file.close()


def test_warn_nonascii():
    # Check that a non-ascii character raises a warning and not an error
    with pytest.warns(SunpyMetadataWarning, match='not valid ascii'):
        fits = header_to_fits({'bad': 'test\t',
                               'good': 'test'})
    assert 'GOOD' in fits.keys()
    assert 'BAD' not in fits.keys()


def test_warn_nan():
    # Check that a NaN value raises a warning and not an error
    with pytest.warns(SunpyMetadataWarning, match='has a NaN value'):
        fits = header_to_fits({'bad': float('nan'),
                               'good': 1.0})
    assert 'GOOD' in fits.keys()
    assert 'BAD' not in fits.keys()


def test_warn_longkey():
    # Check that a key that is too long raises a warning and not an error
    with pytest.warns(SunpyMetadataWarning, match='The meta key badlongkey is too long'):
        fits = header_to_fits({'badlongkey': 'test',
                               'goodkey': 'test'})
    assert 'GOODKEY' in fits.keys()
    assert 'BADLONGKEY' not in fits.keys()


def test_read_memmap():
    # Check that the FITS reader can read a memmap without memmap argument by default
    data, header = sunpy.io._fits.read(TEST_AIA_IMAGE)[0]
    assert isinstance(data.base, mmap.mmap)

    # Check that memmap=True does the same thing
    data, header = sunpy.io._fits.read(TEST_AIA_IMAGE, memmap=True)[0]
    assert isinstance(data.base, mmap.mmap)

    # Check that memmap=False doesn't do memory mapping
    data, header = sunpy.io._fits.read(TEST_AIA_IMAGE, memmap=False)[0]
    assert data.base is None
