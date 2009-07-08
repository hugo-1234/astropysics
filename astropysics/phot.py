#Copyright (c) 2008 Erik Tollerud (etolleru@uci.edu) 
"""
This module is for observed or synthetic photometry and 
related operations.

Tends to be oriented towards optical techniques.
"""

from __future__ import division,with_statement
from math import pi
import numpy as np

from .spec import HasSpecUnits as _HasSpecUnits
try:
    #requires Python 2.6
    from abc import ABCMeta
    from abc import abstractmethod
    from abc import abstractproperty
except ImportError: #support for earlier versions
    abstractmethod = lambda x:x
    abstractproperty = property
    ABCMeta = type
    
    
#<-----------------------Magnitude systems------------------------------------->

class Magnitude(object):
    __metaclass__ = ABCMeta
    @abstractmethod
    def mag_to_flux(self,mag):
        raise NotImplementedError
    @abstractmethod
    def magerr_to_fluxerr(self,err,mag):
        raise NotImplementedError
    @abstractmethod
    def flux_to_mag(self,flux):
        raise NotImplementedError
    @abstractmethod
    def fluxerr_to_magerr(self,err,flux):
        raise NotImplementedError
    
class PogsonMagnitude(Magnitude):
    a = -2.5/np.log(10.0)
    
    def mag_to_flux(self,mag):
        return np.exp(mag/__maga)
    def magerr_to_fluxerr(self,err,mag):
        return -err*_m2f_pogson(mag)/self.a
    def flux_to_mag(self,flux):
        return self.a*np.log(flux)
    def fluxerr_to_magerr(self,err,flux):
        return -self.a*err/flux

class AsinhMagnitude(Magnitude):
    a = -2.5/np.log(10.0)
    
    def __init__(self,b=1e-10):
        self.b = b
        
    def _getb(self):
        return self._b
    def _setb(self,val):
        self._b = val
        self._logb = np.log(b)
    b= property(_getb,_setb)
    
    def mag_to_flux(self,mag):
        return 2*b*np.sinh(mag/self.a-self._logb)
    def magerr_to_fluxerr(self,err,mag):
        b = self.b
        #TODO:fix/test
        return 2*b*err/-self.a*(1+_m2f_asinh(mag)**2)**0.5
    def flux_to_mag(self,flux):
        b = self.b
        return self.a*(np.arcsinh(flux/2/b)+self._logb)
    def fluxerr_to_magerr(self,err,flux):
        #TODO:fix/test
        return -self.a*err/2/b/(1 + (flux/2/b)**2)**0.5


def choose_magnitude_system(system):
    """
    This function is used to change the magnitude system used where
    magnitudes are used in astropysics.  It can be:
    *pogson: mag = -2.5 log10(f/f0)
    *asinh mag = -2.5 log10(e) [asinh(x/2b)+ln(b)] (TODO: choose b from the band or something instead of fixed @ 25 zptmag)
    """
    global _magsys,_mag_to_flux,_magerr_to_fluxerr,_flux_to_mag,_fluxerr_to_magerr
    if isinstance(system,Magnitude):
        _magsys = system
    elif system == 'pogson':
        _magsys = PogsonMagnitude()
    elif system == 'asinh':
        _magsys = AsinhMagnitude(b=1e-10)
    else:
        raise ValueError('unrecognized ')
    
    _mag_to_flux = _magsys.mag_to_flux
    _magerr_to_fluxerr = _magsys.magerr_to_fluxerr
    _flux_to_mag = _magsys.flux_to_mag
    _fluxerr_to_magerr = _magsys.fluxerr_to_magerr   
    
choose_magnitude_system('pogson')

#<---------------------Photometric Classes------------------------------------->

class Band(_HasSpecUnits):
    """
    This class is the base of all photometric band objects.  Bands are expected
    to be immutable once created except for changes of units.
    
    The response functions should be photon-counting response functions (see
    e.g. Bessell et al 2000)
    
    subclasses must implement the following functions:
    *__init__ : initialize the object
    *_getCen : return the center of band 
    *_getFWHM : return the FWHM of the band
    *_getx: return an array with the x-axis
    *_getS: return the photon sensitivity (shape should match x)
    *_applyUnits: units support (see ``astropysics.spec.HasSpecUnits``)
    
    #the following can be optionally overriden:
    *alignBand(x): return the sensitivity of the Band interpolated to the 
                   provided x-array
    *alignToBand(x,S): return the provided sensitivity interpolated onto the 
                       x-array of the Band
    """
    __metaclass__ = ABCMeta
    
    #set default units to angstroms
    _phystype = 'wavelength'
    _unit = 'angstrom'
    _xscaling = 1e-8
    
    @abstractmethod
    def __init__(self):
        raise NotImplementedError
    
    @abstractmethod
    def _getCen(self):
        raise NotImplementedError
    
    @abstractmethod
    def _getFWHM(self):
        raise NotImplementedError
    
    @abstractmethod
    def _getx(self):
        raise NotImplementedError
    
    @abstractmethod
    def _getS(self):
        raise NotImplementedError
    
    #comparison operators TODO:unit matching
    def __eq__(self,other):
        try:
            return np.all(self.x == other.x) and np.all(self.S == other.S)
        except:
            return False
    def __ne__(self,other):
        return not self.__eq__(other)
    def __lt__(self,other):
        oldu = None
        try:
            oldu = other.unit
            other.unit = self.unit
            return self.cen < other.cen
        except:
            return NotImplemented
        finally:
            if oldu is not None:
                other.unit = oldu 
    def __le__(self,other):
        oldu = None
        try:
            oldu = other.unit
            other.unit = self.unit
            return self.cen <= other.cen
        except:
            return NotImplemented
        finally:
            if oldu is not None:
                other.unit = oldu 
    def __gt__(self,other):
        oldu = None
        try:
            oldu = other.unit
            other.unit = self.unit
            return self.cen > other.cen
        except:
            return NotImplemented
        finally:
            if oldu is not None:
                other.unit = oldu 
    def __ge__(self,other):
        oldu = None
        try:
            oldu = other.unit
            other.unit = self.unit
            return self.cen >= other.cen
        except:
            return NotImplemented
        finally:
            if oldu is not None:
                other.unit = oldu 
    
    def __interp(self,x,x0,y0,interpolation):
        """
        interpolate the function defined by x0 and y0 onto the coordinates in x
        
        see Band.alignBand for interpolation types/options
        """
        if interpolation == 'linear':
            return np.interp(x,x0,y0)
        elif 'spline' in interpolation:
            if not hasattr(self,'_splineobj'):
                self._splineobj = None
                
            deg = interpolation.replace('spline','').strip()
            deg = 3 if deg == '' else int(deg)
            if self._splineobj is None or self._splineobj._data[5] != deg:
                from scipy.interp import InterpolatedUnivariateSpline
                self._splineobj = InterpolatedUnivariateSpline(k=deg)
            return self._splineobj(x)
                
        else:
            raise ValueError('unrecognized interpolation type')
    
    
    cen = property(lambda self:self._getCen())
    FWHM = property(lambda self:self._getFWHM())
    x = property(lambda self:self._getx())
    S = property(lambda self:self._getS())
    def _getSrc(self):
        if not hasattr(self._src):
            from .objcat import Source
            self._src = Source(None)
        return self._src
    def _setSrc(self,val=None):
        pass
        #from .objcat import Source
        #self._src = Source(val)
    source = property(_getSrc,_setSrc)
    def _getName(self):
        if self._name is None:
            return 'Band@%4.4g'%self.cen
        else:
            return self._name
    def _setName(self,val):
        self._name = val
    name = property(_getName,_setName)
    _name = None #default is nameless
    
    zptflux = 0 #flux at mag=0
    
    def alignBand(self,x,interpolation='linear'):
        """
        interpolates the Band sensitivity onto the provided x-axis
        
        x can either be an array with the wanted x-axis or a ``Spectrum``
        if it is a spectrum, the units for the band will be converted to 
        the Spectrum units before alignment
        
        interpolation can be 'linear' or 'spline'
        """
        if hasattr(x,'x') and hasattr(x,'unit'):
            units = x.unit
            x = x.x
        oldunit = self.unit
        try:
            self.unit = units
            sorti = np.argsort(self.x)
            return self.__interp(x,self.x[sorti],self.S[sorti],interpolation)
        finally:
            self.unit = oldunit
        
    def alignToBand(self,*args,**kwargs):
        """
        interpolates the provided function onto the Band x-axis
        
        args can be:
        *alignToBand(arr): assume that the provided sequence fills the band and
        interpolate it onto the band coordinates
        *alignToBand(specobj): if specobj is of type ``Spectrum``, the ``Spectrum``
        flux will be returned aligned to the band, in the units of the Band
        *alignToBand(x,y): the function with coordinates (x,y) will be aligned
        to the Band x-axis
        
        keywords:
        *interpolation:see Band.alignBand for interpolation types/options
        """
        if len(args) == 1:
            from operator import isSequenceType
            from .spec import Spectrum,FunctionSpectrum
            specin = args[0]
            
            if isSequenceType(specin):
                y = np.array(specin,copy=False)
                x = np.linspace(self.x[0],self.x[-1])
            elif isinstance(specin,FunctionSpectrum):
                oldx = specin.x
                try:
                    specin.x = self.x
                    return specin.getUnitFlux(self.unit)
                finally:
                    specin.x = oldx
            elif hasattr(specin,'x') and hasattr(specin,'flux'):
                x,y = specin.getUnitFlux(self.unit)
                #x = specin.x
                #y = specin.flux
        elif len(args) == 2:
            x,y = args
        else:
            raise TypeError('alignToBand() takes 1 or 2 arguments')
        
        if 'interpolation' not in kwargs:
            kwargs['interpolation'] = 'linear'
        
        sorti = np.argsort(x)    
        return self.__interp(self.x,x[sorti],y[sorti],kwargs['interpolation'])
    
    def isOverlapped(self,xorspec):
        """
        determes if this Band overlaps on a significant part of the provided 
        spectrum (that is, if center+/-fwhm overlaps) 
        """
        
        if hasattr(xorspec,'x') and hasattr(xorspec,'flux'):
            x = xorspec.x
        else:
            x = xorspec
            
        mx,mn = np.max(x),np.min(x)
        c,w = self.cen,self.FWHM/2
        return (mx >= c+w) and (mn <= c-w)
    
    def computeMag(self,*args,**kwargs):
        """
        Compute the magnitude of the supplied Spectrum in this band using the 
        band's ``zptflux`` attribute
        
        args and kwargs go into Band.computeFlux
        """
        return _flux_to_mag(self.computeFlux(*args,**kwargs)/self.zptflux)
    
    def computeFlux(self,spec,interpolation='linear',aligntoband=None,overlapcheck=True):
        """
        compute the flux in this band for the supplied Spectrum
        
        the Spectrum is aligned to the band if aligntoband is True, or vice 
        versa, otherwise, using the specified interpolation (see Band.alignBand
        for interpolation options).  If aligntoband is None, the higher of the
        two resolutions will be left unchanged 
        
        if overlapcheck is True, a ValueError will be raised if most of the 
        Spectrum does not lie within the band
        
        the spectrum units will be converted to match those of the Band
        
        the spectrum can be an array, but then aligntoband and 
        interpolation are ignored and must match the band's x-axis
        """
        from operator import isSequenceType
        from scipy.integrate import simps as integralfunc
        if isSequenceType(spec):
            x = self.x
            y = np.array(spec)
            if y.shape != x.shape:
                raise ValueError('input array shape does not match Band x-axis')
            units = self.unit
        elif hasattr(spec,'x') and hasattr(spec,'flux'):
            oldunits = spec.unit
            try:
                spec.unit = self.unit
                if aligntoband is None:
                    lx,px = self.x,spec.x
                    aligntoband = lx.size/(lx.max()-lx.min()) > px.size/(px.max()-px.min())
                
                if aligntoband:
                    x = self.x
                    y = self.S*self.alignToBand(spec.x,spec.flux,interpolation=interpolation)
                else:
                    x = spec.x.copy()
                    y = self.alignBand(spec)*spec.flux
            finally:
                spec.unit=oldunits
        else:
            raise ValueError('unrecognized input spectrum')
        
        if overlapcheck and not self.isOverlapped(x):
            raise ValueError('provided input does not overlap on this band')
            
        if 'wavelength' in self.unit:
            y*=x
        else:
            y/=x
            #TODO:check energy factor unit-wise
            
        sorti=np.argsort(x)
        return integralfunc(y[sorti],x[sorti])
    
    def computeZptFromSpectrum(self,*args,**kwargs):
        """
        use the supplied Spectrum as a zero-point Spectrum to 
        define the zero point of this band as well as the flux 
        for that zero-point
        
        args and kwargs are the same as those for computeMag
        """
        #fluxfactor = self.computeFlux(np.ones_like(self.x)) #scale by this factor to get actual flux
        #mag = self.computeMag(*args,**kwargs)
        self.zptflux = self.computeFlux(*args,**kwargs)
        
    
    def plot(self,spec=None,bandscaling=1,bandoffset=0,labelband=True,clf=True,**kwargs):
        """
        this plots the requested band and passes kwargs into matplotlib.pyplot.plot
        OR
        if spec is provided, the spectrum will be plotted along with the band and 
        the convolution
        
        other kwargs:
        *clf : clear the figure before plotting
        *leg : show legend where appropriate
        """
        from matplotlib import pyplot as plt
        band = self
        
        if clf:
            plt.clf()
                
        if spec:
            from .spec import Spectrum
            if not isinstance(spec,Spectrum):
                raise ValueError('input not a Spectrum')
            bandscaling = np.max(spec.flux)*bandscaling
            convflux = band.alignToBand(spec)*band.S
            
            plt.plot(band.x,bandscaling*band.S+bandoffset,c='k',label='$S_{\\rm Band}$')
            bandmax = bandscaling*band.S.max()+bandoffset
            plt.plot(spec.x,spec.flux,c='g',ls=':',label='$f_{\\rm spec}$')
            plt.plot(band.x,convflux,c='b',ls='--',label='$f_{\\rm spec}S_{\\rm Band}$')
            
            plt.ylabel('Spec flux or S*max(spec)')
            if kwargs.pop('leg',True):
                plt.legend(loc=0)
            mi,ma=band.x.min(),band.x.max()
            rng = ma-mi
            plt.xlim(mi-rng/3,ma+rng/3)
        else:
            bandmax = bandscaling*band.S.max()+bandoffset
            plt.plot(band.x,bandscaling*band.S+bandoffset,**kwargs)
            plt.ylabel('$S$')
            plt.ylim(0,bandscaling*band.S.max())
            
        if labelband and self.name is not None:
            plt.text(band.cen,bandmax,self.name)
        plt.xlabel('$\\lambda$')
            

class GaussianBand(Band):
    def __init__(self,center,width,A=1,sigs=6,n=100,unit='angstroms',name=None):
        """
        center is the central wavelength of the band, while width is the sigma 
        (if positive) or FWHM (if negative)
        """
        self._cen = center
        self._sigma = width if width > 0 else -width*(8*np.log(2))**-0.5
        self._fwhm = self._sigma*(8*np.log(2))**0.5
        self._A = A
        
        self._n = n
        self._sigs = sigs
        self._updateXY(self._cen,self._sigma,self._A,self._n,self._sigs)
        
        _HasSpecUnits.__init__(self,unit)
        self._unittrans = (lambda t:t,lambda t:t)
        
        self.name = name
        
    def _applyUnits(self,xtrans,xitrans,xftrans,xfinplace):
        self._unittrans = (xtrans,xftrans,xitrans)
        self._updateXY(self._cen,self._sigma,self._A,self._n,self._sigs)
        
    def _updateXY(self,mu,sigma,A,n,sigs):
        xtrans,xftrans,xitrans = self._unittrans
        
        x = np.linspace(-sigs*sigma,sigs*sigma,n)+mu
        xp = (self._x-mu)/sigma
        y = A*np.exp(-xp*xp/2)
        self._x,self._y = xftrans(x,y)
        
    def _getSigs(self):
        return self._sigs
    def _setSigs(self,val):
        self._updateXY(self._cen,self._sigma,self._A,self._n,val)
        self._sigs = val
    sigs = property(_getSigs,_setSigs)
    
    def _getn(self):
        return self._n
    def _setn(self,val):
        self._updateXY(self._cen,self._sigma,self._A,val,self._sigs)
        self._n = val
    n = property(_getn,_setn)

    @property
    def sigma(self):
        return self.unittrans[0](self._sigma)
    
    def _getCen(self):
        return self.unittrans[0](self._cen)
    
    def _getFWHM(self):
        return self.unittrans[0](self._fwhm) #=sigma*(8*log(2))**0.5
    
    def _getx(self):
        return self._x
    
    def _getS(self):
        return self._y
    
    def alignBand(self,x):
        xtrans,xftrans,xitrans = self._unittrans
        oldx = xitrans(x)
        xp = (x-self._cen)/self._sigma 
        return xftrans(oldx,self._A*np.exp(-xp*xp/2))[1]
        
class ArrayBand(Band):
    def __init__(self,x,S,copyonaccess=True,normalized=True,unit='angstroms',name=None):
        """
        generate a Band from a supplied quantum (e.g. photonic) response 
        function 
        
        if the response function is ever negative, the band will be offset so
        that the lowest point is 0 .  If the band x-axis is not sorted, it 
        will be sorted from lowest to highest.
        """
        self._x = np.array(x,copy=True)
        self._S = np.array(S,copy=True)
        sorti = np.argsort(self._x)
        self._x,self._S = self._x[sorti],self._S[sorti]

        if self._x.shape != self._S.shape or len(self._x.shape) != 1:
            raise ValueError('supplied x and S are not matching 1D arrays')
        if self._S.min() < 0:
            self._S -= self._S.min()
        self._N = self._S.max()
        if normalized:
            self._S /= self._N
        self.copyonaccess = copyonaccess
        self._norm = normalized
        
        self._computeMoments()
        
        _HasSpecUnits.__init__(self,unit)
        
        self.name = name
        
    #units support
    def _applyUnits(self,xtrans,xitrans,xftrans,xfinplace):
        xfinplace(self._x,self._S) 
        mx = self._S.max()
        self._S/=mx
        if not self._norm:
            self._S/=self._N
        self._computeMoments() #need to recompute moments
        
    def _computeMoments(self):
        from scipy.integrate import  simps as integralfunc
        #trapz vs. simps: trapz faster by factor ~5,simps somewhat more accurate
        x=self._x
        y=self._S/self._S.max()
        N=1/integralfunc(y,x)
        yn = y*N #normalize so that overall integral is 1
        self._cen = integralfunc(x*yn,x)
        xp = x - self._cen
        
        
        if y[0] > 0.5 or y[-1] > 0.5:
            self._fwhm = (integralfunc(xp*xp*yn,xp)*8*np.log(2))**0.5 
        else:
            #from scipy.interpolation import interp1d
            #from scipy.optimize import newton
            #ier = interp1d(x,y-0.5)
            #lval-uval=newton(ier,x[0])-newton(ier,x[-1])
            #need peak to be 1 for this algorithm
            yo = y-0.5
            edgei = np.where(yo*np.roll(yo,1)<0)[0]-1
            li,ui = edgei[0]+np.arange(2),edgei[1]+np.arange(2)
            self._fwhm = np.interp(0,yo[ui],x[ui])-np.interp(0,yo[li],x[li])
            
    
    def _getNorm(self):
        return self._norm
    def _setNorm(self,val):
        val = bool(val)
        if val != self._norm:
            if self._norm:
                self.S *= self._N
            else:
                self.S /= self._N
        self._norm = val
    normalized = property(_getNorm,_setNorm)
        
    def _getCen(self):
        return self._cen
    
    def _getFWHM(self):
        return self._fwhm
    
    def _getx(self):
        if self.copyonaccess:
            return self._x.copy()
        else:
            return self._x
    
    def _getS(self):
        if self.copyonaccess:
            return self._S.copy()
        else:
            return self._S
        
        
class FileBand(ArrayBand):
    def __init__(self,fn,type=None):
        """
        type can be 'txt', or 'fits', or inferred from extension
        
        if txt, first column should be lambda, second should be response
        """
        from os import path
        
        self.fn = fn
        if type is None:
            ext = path.splitext(fn)[-1].lower()
            if ext == 'fits' or ext == 'fit':
                type = 'fits'
            else:
                type = 'txt'
        
        if type == 'txt':
            x,S = np.loadtxt(fn).T
        elif type == 'fits':
            import pyfits
            f = pyfits.open(fn)
            try:
                #TODO: much smarter/WCS
                x,S = f[0].data
            finally:
                f.close()
        else:
            raise ValueError('unrecognized type')
        
        ArrayBand.__init__(self,x,S)
        
        
def plot_band_group(bandgrp,**kwargs):
    """
    this will plot a group of bands on the same plot
    
    group can be a sequnce of bands, strings or a dictionary mapping names to
    bands
    
    kwargs go into Band.plot except for:
    *clf : clear figure before plotting
    *leg : show legend with band names
    *unit : unit to use on plots (defaults to angstroms)
    *c : (do not use)
    *spec : (do not use)
    """
    from matplotlib import pyplot as plt
    from operator import isMappingType,isSequenceType
    
    
    if isMappingType(bandgrp):
        names = bandgrp.keys()
        bs = bandgrp.values()
    else:
        names,bs = [],[]
        for b in bandgrp:
            if type(b) is str:
                names.append(b)
                bs.append(bands[b])
            else:
                names.append(b.name)
                bs.append(b)

    d = dict([(n,b) for n,b in  zip(names,bs)])
    sortednames = sorted(d,key=d.get)
    
    clf = kwargs.pop('clf',True)
    leg = kwargs.pop('leg',True)
    kwargs.pop('spec',None)
    cs = kwargs.pop('c',None)
    unit = kwargs.pop('unit','wl')
       
    oldunits = [b.unit for b in bs]
    try:
        for b in bs:
            b.unit = unit
    except NotImplementedError:
        pass
    
    
    if clf:
        plt.clf()
    
    bluetored = 'wavelength' in bs[0].unit
    
    if cs is None:
        
        x = np.arange(len(bs))
        b = 1-x*2/(len(x)-1)
        g = 1-2*np.abs(0.5-x/(len(x)-1))
        g[g>0.5] = 0.5
        r = (x*2/(len(x)-1)-1)
        r[r<0] = b[b<0] = 0
        
        if not bluetored:
            b,r = r,b
        cs = np.c_[r,g,b]
        
        #custom coloring for UBVRI and ugriz
        if len(sortednames) == 5:
            if sortednames[:3] == ['U','B','V']:
                cs = ['c','b','g','r','m']
            elif np.all([(n in sortednames[i]) for i,n in enumerate(('u','g','r','i','z'))]):
                cs = ['c','g','r','m','k']
        
    
    kwargs['clf'] = False
    for n,c in zip(sortednames,cs):
        kwargs['label'] = n
        kwargs['c'] = c
        d[n].plot(**kwargs)
    
    if leg:
        plt.legend(loc=0)
    
    try:
        for u,b in zip(oldunits,bs):
            b.unit = u
    except (NameError,NotImplementedError),e:
        print 'hit'
        pass
    
    
def compute_band_zpts(specorscale,bands):
    """
    this will use the supplied spectrum to determine the magnitude zero points
    for the specified bands 
    OR
    scale the zeropoint 
    """
    bnds = str_to_bands(bands)
    
    if np.isscalar(specorscale):
        for b in bnds:
            b.zptflux *= specorscale
    else:
        for b in bnds:
            b.computeZptFromSpectrum(specorscale)
            
def set_zeropoint_system(system,bands='all'):
    """
    this uses a standard system to apply the zeropoints for the specified band
    names.
    
    system can be:
    * 'AB' - use AB magnitudes
    * 'vega' - use vega=0 magnitudes based on Kurucz '93 Alpha Lyrae models
    * 'vega##' - use vega=## magnitudes based on Kurucz '93 Alpha Lyrae models
    """
    
    from .spec import Spectrum,FunctionSpectrum,ABSpec
    bands = str_to_bands(bands)
    
    if system == 'AB':
        s = ABSpec.copy()
        for b in bands:
            s.unit = b.unit
            s.x = b.x
            b.computeZptFromSpectrum(s,aligntoband=True,interpolation='linear')
        
    elif 'vega' in system.lower():
        from cPickle import loads
        from .io import _get_package_data
        
        try:
            offset = float(system.lower().replace('vega',''))
        except ValueError:
            offset = 0

        vegad = loads(_get_package_data('vega_k93.pydict'))['data']
        s = Spectrum(vegad['WAVELENGTH'],vegad['FLUX']*10**(offset/2.5))
        
        for b in bands:
            b.computeZptFromSpectrum(s)
    else:
        raise ValueError('unrecognized magnitude system')
    
    
class PhotObservation(object):
    """
    A photometric measurement (or array of measurements) in a fixed 
    group of bands.  These bands must be present in the band registry.
    
    the first index of the values must have length equal to nbands
    
    if asmags is True, values and errs will be interpreted as magnitudes,
    otherwise, flux
    """
    
    def __init__(self,bands,values,errs=None,asmags=True):
        self._bandnames = tuple([b.name for b in str_to_bands(bands)])
            
        if asmags:
            self.mag = values
            if errs is None:
                errs = np.zeros_like(values) 
            elif np.isscalar(errs):
                errs = errs*np.ones_like(values) 
            self.magerr = errs
        else:
            self.flux = values
            if errs is None:
                errs = np.zeros_like(values) 
            elif np.isscalar(errs):
                errs = errs*np.ones_like(values) 
            self.fluxerr = errs
            
    def __str__(self):
        ss = ['Band %s:%s'%(bn,v) for bn,v in zip(self.bandnames,self._values)]
        ss.append('(mag)' if self._mags else '(flux)')
        return ' '.join(ss)
            
    def __len__(self):
        return len(self._bandnames)
    
    @property
    def bandnames(self):
        return self._bandnames
    
    @property
    def bands(self):
        return str_to_bands(self._bandnames)
    
    def _zeroPoints(self):
        return np.array([b.zptflux for b in self.bands])
    
    def _getMags(self):
        if self._mags:
            return self._values.copy()
        else:  
            zptfluxes = self._zeroPoints()
            zptfluxes = zptfluxes.reshape((zptfluxes.size,1))
            if len(self._values.shape)==1:
                return _flux_to_mags(self._values.reshape(zpts.shape)/zptfluxes).ravel()
                #return (-2.5*np.log10(self._values.reshape(zpts.shape))-zpts).ravel()
            else:
                return _flux_to_mags(self._values)
                #return -2.5*np.log10(self._values)-zpts
    def _setMags(self,val):
        if len(val) != len(self._bandnames):
                raise ValueError('input length does not match number of bands')
        self._mags = True
        self._values = np.array(val)
    mag = property(_getMags,_setMags,doc='photmetric measurements in magnitudes')
    def _getMagsErr(self):
        if self._mags:
            return self._err
        else:
            return _fluxerr_to_magerr(self._err,self._values)
            #return -2.5/np.log(10)*self._err/self._values
    def _setMagsErr(self,val):
        val = np.array(val)
        if val.shape != self._values.shape:
            raise ValueError("Errors don't match values' shape")
        if self._mags:
            self._err = val
        else:
            self._err = _magerr_to_fluxerr(val,self.mag)
            #self._err = self._values*val*np.log(10)/-2.5
    magerr = property(_getMagsErr,_setMagsErr,doc='photmetric errors in magnitudes')
    
    def _getFlux(self):
        if self._mags:
            zptfluxes = self._zeroPoints()
            zptfluxes = zptfluxes.reshape((zptfluxes.size,1))
            if len(self._values.shape)==1:
                return zptfluxes[:,0]*_mag_to_flux(self._values)
                #return (10**((self._values.reshape(zpts.shape)+zpts)/-2.5)).ravel()
            else:
                return zptfluxes*_mag_to_flux(self._values)
                #return 10**((self._values+zpts)/-2.5)
        else:  
            return self._values.copy()
    def _setFlux(self,val):
        if len(val) != len(self._bandnames):
                raise ValueError('input length does not match number of bands')
        self._mags = False
        self._values = np.array(val)
    flux = property(_getFlux,_setFlux,doc='photmetric measurements in flux units')
    def _getFluxErr(self):
        if self._mags:
            zptfluxes = self._zeroPoints()
            zptfluxes = zptfluxes.reshape((zptfluxes.size,1))
            if len(self._values.shape)==1:
                return zptfluxes[:,0]*_magerr_to_fluxerr(self._err,self._values)
            else:
                return zptfluxes*_magerr_to_fluxerr(self._err,self._values)
            #return _magerr_to_fluxerr(self._err,self._values)
            #return self.flux*self._err*np.log(10)/-2.5
        else:
            return self._err.copy()
    def _setFluxErr(self,val):
        val = np.array(val)
        if val.shape != self._values.shape:
            raise ValueError("Errors don't match values' shape")
        if self._mags:
            self._err = _fluxerr_to_magerr(val,self.mag)
            #self._err = -2.5/np.log(10)*val/self.flux
        else:
            self._err = val
    fluxerr = property(_getFluxErr,_setFluxErr,doc='photmetric errors in flux units')
    
    def getFluxDensity(self,unit='angstroms'):
        """
        compute an approximate flux density (e.g. erg cm^-2 s^-1 angstrom^-1)
        assuming flat over the FWHM        
        """
        f,e = self.flux,self.fluxerr
        x,w = self.getBandInfo(unit)
        if len(f.shape) > 1:
            w = np.tile(w,f.size/len(x)).reshape((len(x),f.size/len(x)))
        
        return f/w,e/w
    
    def getBandInfo(self,unit='angstroms'):
        """
        Extracts the center and FWHM of the bands in these observations
        
        returns x,w
        """
        x=[]
        w=[]
        for b in self.bands:
            oldunit = b.unit
            b.unit = unit
            x.append(b.cen)
            w.append(b.FWHM)
            b.unit = oldunit
        return np.array(x),np.array(w)
    
    def toSpectrum(self,unit='angstroms'):
        """
        converts this data set to a Spectrum
        
        TODO: fill in gaps assuming a flat spectrum
        """
        from .spec import Spectrum
        
        y = self.flux
        err = self.fluxerr
        
        x=[]
        w=[]
        for b in self.bands:
            oldunit = b.unit
            b.unit = unit
            x.append(b.cen)
            w.append(b.FWHM)
            utype = b._phystype
            b.unit = oldunit
            
        x = np.tile(x,np.prod(y.shape)/y.shape[0]).reshape((y.shape))
        w = np.tile(w,np.prod(y.shape)/y.shape[0]).reshape((y.shape))
        return Spectrum(x,y/w,err/w,unit=unit)
    
    def plot(self,includebands=True,fluxtype=None,unit='angstroms',clf=True,**kwargs):
        """
        plots these photometric points
        
        fluxtype can be:
        *None: either magnitude or flux depending on the input type
        *'mag': magnitudes
        *'flux': flux in erg cm^-2 s^-1
        *'fluxden': flux spectral density e.g. erg cm^-2 s^-1 angstroms^-1
        
        kwargs go into matplotlib.pyplot.errorbar
        """
        from matplotlib import pyplot as plt
        
        if fluxtype is None:
            asmags = self._mags
            den = False
        elif fluxtype == 'mag':
            asmags = True
            den = False
        elif fluxtype == 'flux':
            asmags = False
            den = False
        elif fluxtype == 'fluxden':
            asmags = False
            den = True
        else:
            raise ValueError('unrecognized fluxtype')
            
        bands = self.bands
        nb = len(bands) 
        
        if asmags:
            y = self.mag
            yerr = self.magerr
        elif den:
            y,yerr = self.getFluxDensity(unit=unit)
        else:
            y = self.flux
            yerr = self.fluxerr
            
        npts = np.prod(y.shape)/nb
        y,yerr=y.reshape((nb,npts)),yerr.reshape((nb,npts))
        
        x=[]
        #w=[]
        for b in bands:
            oldunit = b.unit
            b.unit = unit
            x.append(b.cen)
            #w.append(b.FWHM)
            utype = b._phystype
            b.unit = oldunit
        x = np.tile(x,npts).reshape((nb,npts))
        #w = np.tile(w,npts).reshape((nb,npts))
            
        if clf:
            plt.clf()
            
        if 'fmt' not in kwargs:
            kwargs['fmt'] = 'o'
        if 'ecolor' not in kwargs:
            kwargs['ecolor'] = 'k'
        plt.errorbar(x.ravel(),y.ravel(),yerr.ravel() if np.any(yerr) else None,**kwargs)
       
        if includebands:
            if includebands is True:
                includebands = {}
            if 'bandscaling' not in includebands:
                includebands['bandscaling'] = 0.5*(y.max()-y.min())
            if 'bandoffset' not in includebands:
                includebands['bandoffset'] = y.min()
            if 'ls' not in includebands:
                includebands['ls'] = '--'
            if 'leg' not in includebands:
                includebands['leg'] = False
            includebands['clf'] = False
            
            xl = plt.xlim()
            plot_band_group(bands,**includebands)
            plt.xlim(*xl)
            
        if utype == 'wavelength':
            plt.xlabel('$\\lambda$')
        elif utype=='frequency':
            plt.xlabel('$\\nu$')
        else:
            plt.xlabel(unit)
        plt.ylabel('Mag' if asmags else 'Flux[${\\rm erg} {\\rm s}^{-1} {\\rm cm}^{-2} {%s}^{-1}$]'%unit)
        rng = y.max() - y.min()
        plt.ylim(y.min()*1.05-y.max()*.05,y.min()*-0.05+y.max()*1.05)

#<---------------------Analysis Classes/Tools---------------------------------->

class CMDAnalyzer(object):
    """
    This class is intended to take multi-band photometry and compare it
    to fiducial models to find priorities/matches for a set of data from the
    same bands
    """
    
    @staticmethod
    def _dataAndBandsToDicts(bandsin,arr):
        from warnings import warn
        from operator import isSequenceType
        
        if len(bandsin) != arr.shape[0]:
            raise ValueError('bandsin does not match fiducial bands')
        
        n = arr.shape[1]
        
        bandnames,bandobjs,colors=[],[],[]
        for b in bandsin:
            if type(b) is str:
                if '-' in b:
                    bandnames.append(None)
                    bandobjs.append(None)
                    colors.append(b)
                else:
                    bandnames.append(b)
                    bandobjs.append(bands[b])
                    colors.append(None)
            elif hasattr(b,'name'):
                bandnames.append(b.name)
                bandobjs.append(b)
                colors.append(None)
            else:
                raise ValueError("Can't understand input band "+str(b))
            
        bd={}
        datad={}
        maskd = {}
        for i,(n,b) in enumerate(zip(bandnames,bandobjs)):
            if b is not None:
                if n is None:
                    bd[b.name] = b
                    datad[b.name] = arr[i]
                    maskd[b.name] = True
                else:
                    bd[n] = b
                    datad[n] = arr[i]
                    maskd[n] = True
                    
        for i,c in enumerate(colors):
            if c is not None:
                b1,b2 = (b.strip() for b in c.split('-'))
                if b1 in bd and not b2 in bd:
                    bd[b2] = bands[b2]
                    datad[b2] = datad[b1] - arr[i]
                    maskd[b2] = True
                elif b2 in bd and not b1 in bd:
                    bd[b1] = bands[b1]
                    datad[b1] = arr[i] + datad[b2]
                    maskd[b1] = True
                elif b1 in bd and b2 in bd:
                    warn('Bands %s and %s overedetermined due to color %s - using direct band measurements'%(b1,b2,c))
                    #do nothing because bands are already defined
                else:
                    warn('Bands %s and %s underdetermined with only color %s - assuming zeros for band %s'%(b1,b2,c,b1))
                    bd[b1] = bands[b1]
                    datad[b1] = np.zeros(len(arr[i]))
                    maskd[b1] = False
                    bd[b2] = bands[b2]
                    datad[b2] = -1*arr[i]
                    maskd[b2] = True
                
        return bd,datad,maskd
    
    def __init__(self,fiducial,fbands,fidname='fiducial'):
        """
        fiducial is a B x N array where B is the number of bands/colors
        and N is the number of fiducial points.  
        
        fbands specifies the band (either as a string or a Band object) or 
        color name (seperated by "-") matching the fiducial
        
        fidname is a string or a dictionary that maps fiducial names to 
        indecies in the fidcuial array.  If a dictionary, each index must 
        be in one of the values (but not in more than one)
        """
        from warnings import warn
        from operator import isSequenceType
        
        arr = np.atleast_2d(fiducial)
        bandd,datad,maskd = self._dataAndBandsToDicts(fbands,arr)
                
        self._banddict = bandd
        self._fdatadict = datad 
        self._dm0fdd = datad #distance modulus 0 data
        self._dmod = 0
        self._bandnames = tuple(sorted(bandd.keys(),key=bandd.get))
        self._fidmask = np.array([maskd[b] for b in self._bandnames])
        self._fmaskd = maskd
        self._nb = len(self._bandnames)
        self._nfid = arr.shape[1]
        
        if isinstance(fidname,basestring):
            self._fidnamedict={fidname:np.arange(self._nfid)}
        else:
            d,vals = {},[]
            vals = []
            for k,v in fidname.iteritems():
                d[k] =  np.array(v,dtype=int)
                vals.extend(d[k])
            if not np.all(np.sort(vals) == np.arange(self._nfid)):
                raise ValueError('fidname dictionary does not account for all fiducial array elements or duplicate names')
            self._fidnamedict = d
        
        self._data = None
        self._datamask = np.zeros(self._nb,dtype=bool)
        self._nd = 0
        self._cen = (0,0,0)
        self._locs = None
        self._dnames = None
        self._dgrp = None
        
        self._offsets  = None
        
        self._offbands = None
        self._offws = None
        self._locw = 1
        
        
        
    def _calculateOffsets(self):
        #use self._offbands and self._dmod to set self._offsets
        if self._offbands is None:
            bands = [self._bandnames[i] for i,b in enumerate(self._fidmask & self._datamask) if b]
            fids = np.array([self._fdatadict[b]+self._dmod for b in bands],copy=False).T
            #fids = np.array([self.getFiducialData(b) for b in bands],copy=False).T
            lbds = list(self._bandnames)
            data = np.array([self._data[lbds.index(b)] for b in bands],copy=False).T
        else:
            lbns=list(self._bandnames)
            
            #first check to make sure offset bands are valid
            for b in self._offbands:
                if isinstance(b,tuple):
                    i1 = lbns.index(b[0])
                    i2 = lbns.index(b[1])
                    assert (isinstance(i1,int) and i1 >=0 and i1 < self._nb),(i1,b1)
                    assert (isinstance(i2,int) and i2 >=0 and i2 < self._nb),(i2,b2)
                    if not ((self._fidmask[i1] and self._datamask[i1]) or  (self._fidmask[i2] and self._datamask[i2])):
                        raise ValueError('masks incompatible with bands at positions %i and %i'%(i1,i2))
                else:
                    i = lbns.index(b)
                    assert (isinstance(i,int) and i >=0 and i < self._nb),(i,b)
                    if not self._datamask[i]:
                        raise ValueError('data mask incompatible with band at position %i'%i)
                    if not self._fidmask[i]:
                        raise ValueError('fiducial mask incompatible with band at position %i'%i)
            
            
            #now do the calculations
            fids,dats = [],[]
            
            for b in self._offbands:
                if isinstance(b,tuple):
                    fids.append(self._fdatadict[b[0]]-self._fdatadict[b[1]])
                    dats.append(self._data[lbns.index(b[0])]-self._data[lbns.index(b[1])])
                else:
                    fids.append(self._fdatadict[b]+self._dmod)
                    #fids.append(self.getFiducialData(b))
                    dats.append(self._data[lbns.index(b)])
            fids,data = np.array(fids,copy=False).T,np.array(dats,copy=False).T
            
        #TODO:interpolate along fiducials to a reasonable density
        #dims here: fids = nfXnb and data = ndXnb
        datat = np.tile(data,(fids.shape[0],1,1)).transpose((1,0,2))
        diff = (fids - datat)
        
        if self._offws is not None:
            ws = self._offws
            m = ws<0
            if np.any(m):
                ws = ws.copy().astype(float)
                ws[m] = -ws[m]/(diff[:,:,m].max(axis=1).max(axis=0)-diff[:,:,m].min(axis=1).min(axis=0))
            diff *= ws
        
        sepsq = np.sum(diff*diff,axis=2)
        sepsq = np.min(sepsq,axis=1) #CMD offset
        if self._locw and self._locs is not None:
            locsep = self.locs.T-self.center[:self.locs.shape[0]]
            sepsq = sepsq + self._locw*np.sum(locsep*locsep,axis=1)
        self._offsets = sepsq**0.5
        
    def getBand(self,i):
        if isinstance(i,int):
            return self._banddict[self._bandnames[i]]
        elif isinstance(i,basestring):
            return self._banddict[i]
        raise TypeError('Band indecies must be band names or integers')
    
    def getFiducialData(self,i,fidname=None):
        """
        Retreives fiducial data values in a particular band.  
        
        i is either an index into the bands, or a band name.
    
        fidname specifies which fiducial sequence to use (or if None,
        the full array for the requested band will be returned)
        """
        if fidname is None:
            mask = np.arange(self._nfid)
        else:
            mask = self._fidnamedict[fidname]
        if isinstance(i,int):
            return self._fdatadict[self._bandnames[i]][mask]+self._dmod
        elif isinstance(i,basestring):
            if '-' in i:
                b1,b2 = i.split('-')
                b1,b2 = b1.strip(),b2.strip()
                if (b1 not in self._fmaskd and b2 not in self._fmaskd) or (not self._fmaskd[b1] and not self._fmaskd[b2]):
                    raise ValueError('%s and %s are not valid fiducial bands'%(b1,b2))
                
                c = self._fdatadict[b1][mask] - self._fdatadict[b2][mask]
                return c
            else:
                b = i.strip()
                if b not in self._fmaskd or not self._fmaskd[b]:
                    raise ValueError('%s is not a valid fiducial band'%b)
                return self._fdatadict[b][mask]+self._dmod
        else:
            return self._fdatadict[i][mask]+self._dmod
        raise TypeError('Band indecies must be band names or integers')
    
    @property
    def fidnames(self):
        return self._fidnamedict.keys()
    
    @property
    def bandnames(self):
        return self._bandnames
    
    @property
    def validbandnames(self):
        return [b for i,b in enumerate(self._bandnames) if self._datamask[i] and self._fidmask[i]]
    
    @property
    def validbandinds(self):
        return [i for i,b in enumerate(self._bandnames) if self._datamask[i] and self._fidmask[i]]
    
    def getData(self,i=None):
        if i is None:
            return self._data
        elif isinstance(i,int):
            return self._data[i]
        elif isinstance(i,basestring):
            lbn=list(self._bandnames)
            if '-' in i:
                b1,b2 = i.split('-')
                b1,b2=b1.strip(),b2.strip()
                if b1 not in self.validbandnames and b2 not in self.validbandnames:
                    raise ValueError('%s and %s are not valid bands'%(b1,b2))
                #if b2 not in self.validbandnames:
                #    raise ValueError('%s is not a valid band'%b2)
                return self._data[lbn.index(b1)] - self._data[lbn.index(b2)]
            else:
                if i not in self.validbandnames:
                    raise ValueError('%s is not a valid band'%i)
                return self._data[lbn.index(i)]
        else:
            raise ValueError('unrecognized data type')
    def setData(self,val):
        """
        This loads the data to be compared to the fiducial sequence - the input
        can be an array (B X N) or an 
        """
        from operator import isMappingType
        if isMappingType(val):
            bandd,datad,maskd = self._dataAndBandsToDicts(val.keys(),np.atleast_2d(val.values()))
            
            arrinddict = {}
            currnd = None
            for b,d in datad.iteritems():
                if b in self._bandnames:
                    bi = list(self._bandnames).index(b)
                    if maskd[b]:
                        if currnd and len(d) != currnd:
                            raise ValueError('Band %s does not match previous band sizes'%b)
                        currnd = len(d)
                        arrinddict[bi] = d
                else:
                    from warnings import warn
                    warn('input data includes band %s not present in fiducial'%b)
                        
            mask,dat = [],[]
            for delem in [arrinddict.pop(i,None) for i in range(self._nb)]:
                if delem is None:
                    mask.append(False)
                    dat.append(np.NaN*np.empty(currnd))
                else:
                    mask.append(True)
                    dat.append(delem)
                    
            self._data = np.array(dat)
            self._datamask = np.array(mask,dtype=bool)
            self._nd = currnd
            
        else:
            if len(val) != self._nb:
                raise ValueError('input sequence does not match number of bands')
            self._data = arr = np.atleast_2d(val)
            self._nd = arr.shape[1]
            self._datamask = np.ones(arr.shape[0],dtype=bool)
            
        #check to make sure the offset bands are ok for the new data
        try:
            self.offsetbands = self.offsetbands
        except ValueError:
            print 'new data incompatible with current offset bands - setting to use all'
            self._offbands = None
        
        #need to recalculate offsets with new data
        self._offsets = None 
        #similarly for locs and names - assume new data means new objects
        self._locs = None
        self._dnames = None
    data = property(getData,setData,doc='\nsee ``getData`` and ``setData``')
        
        
    def _getLocs(self):
        return self._locs
    def _setLocs(self,val):
        
        if val is None:
            self._locs = None
        else:
            arr = np.atleast_2d(val)
            if arr.shape[0] < 2 or arr.shape[0] > 3:
                raise ValueError('locations must have either two componets or three')
            if arr.shape[1] != self._nd:
                raise ValueError('location data must match photometric data')
            self._locs = arr
    locs = property(_getLocs,_setLocs,doc="""
    The physical location of the data for prioritizing based on distance
    """)
    def _getDName(self):
        if self._dnames is None:
            return [str(i+1) for i in range(self._nd) ]
        else:
            return list(self._dnames)
    def _setDName(self,val):
        if len(val) != self._nd:
            raise ValueError('number of names do not match number of data points')
        self._dnames = tuple(val)
    datanames = property(_getDName,_setDName,doc="""
    Names for the objects - default is in numerical order starting at 1
    """)
    
    def _getDGrp(self):
        return self._dgrp
    def _setDGrp(self,val):
        if val is None:
            self._dgrp = None
            return
        if len(val) != self._nd:
            raise ValueError('number of group numbers do not match number of data points')
        self._dgrp = np.array(val,dtype=int)
    datagroups = property(_getDGrp,_setDGrp,doc="""
    Group numbers for the objects - will be cast to ints.
    Typical meanings:
    0 -> don't use in spectrum
    -1 -> alignment or guide star
    """)
    
    def _getCen(self):
        return self._cen
    def _setCen(self,val):
        if val is None:
            self._cen = (0,0,0)
        else:
            if len(val) == 2:
                self._cen = (val[0],val[1],0)
            elif len(val) == 3:
                self._cen = tuple(val)
            else:
                raise ValueError('locations must have either two componets or three')
    center = property(_getCen,_setCen,doc="""
    The center of the data for prioritizing based on distance
    """)
            
    def _getOffBands(self):
        if self._offbands is None:
            return None
        return ['%s-%s'%e if isinstance(e,tuple) else e for e in self._offbands]
    
    def _setOffBands(self,val):
        from operator import isSequenceType
        
        if val is None:
            self._offbands = None
        else:
            op = []
            lbn = list(self._bandnames)
            for i,v in enumerate(val):
                if isinstance(v,basestring):
                    try:
                        vs = v.split('-')
                        if len(vs) == 2:
                            b1,b2 = vs
                            op.append((lbn.index(b1.strip()),lbn.index(b2.strip())))
                        else:
                            op.append(lbn.index(v.strip()))
                    except:
                        raise ValueError('uninterpretable band type in position %i'%i)
                elif isinstance(v,int):
                    op.append(v)
                else:
                    try:
                        b1,b2 = v
                        if isinstance(b1,basestring):
                            op.append(lbn.index(b1))
                        else:
                            op.append(b1)
                        if isinstance(b2,basestring):
                            op.append(lbn.index(b2))
                        else:
                            op.append(b2)
                    except:
                        raise ValueError('uninterpretable band type in position %i'%i)
                    
            bandkeys = []
            for v in op:
                if isinstance(v,tuple):
                    bandkeys.append((self._bandnames[v[0]],self._bandnames[v[1]]))
                else:
                    bandkeys.append(self._bandnames[v])
    
            self._offbands = bandkeys
        #need to recalculate offsets with new data
        self._offsets = None 
        #offset weights are now invalid
        self._offws = None
        
        
    offsetbands = property(_getOffBands,_setOffBands,doc="""
    this selects the bands or colors to use in determining offsets
    as a list of band names/indecies (or for colors, 'b1-b2' or a 2-tuple)
    if None, all the bands will be used directly.
    """)
        
    def getOffsets(self):
        """
        computes and returns the CMD offsets
        """
        if self._data == None:
            raise ValueError("data not set - can't compute offsets")
        if self._offsets is None:
            self._calculateOffsets()
        return self._offsets
    def clearOffsets(self):
        """
        clears the offsets for setting of properties without recalculation
        """
        self._offsets = None
    
    def _getDist(self):
        return distance_from_modulus(self.distmod)
    def _setDist(self,val):
        self.distmod = distance_modulus(val)
    distance = property(_getDist,_setDist,doc="""
    The distance to use in calculating the offset between the fiducial values 
    and the data
    """)
    def _getDMod(self):
        return self._dmod
    def _setDMod(self,val):
#        if val == 0:
#            self._fdatadict = self._dm0fdd
#        else:
#            newd = {}
#            for b,arr in self._dm0fdd.iteritems():
#                newd[b] =  arr+val
#            self._fdatadict = newd
        self._dmod = val
        #need to recalculate offsets with new data
        self._offsets = None
    distmod = property(_getDMod,_setDMod,doc="""
    The distance modulusto use in calculating the offset 
    between the fiducial values and the data 
    """)
    def _getOffWs(self):
        if self._offws is None:
            return np.ones(len(self._offbands))
        else:
            return self._offws
    def _setOffWs(self,val):
        if val is None:
            self._offws = None
            return
        if (self._offbands is None and len(val) != self._nb) or (len(val)!=len(self._offbands)):
            raise ValueError('offset length does not match weights')
        self._offws = np.array(val)
        self._offsets = None
    offsetweights = property(_getOffWs,_setOffWs,doc="""
    Weights to apply to bands while calculating the offset. 
    Note that this will be invalidated whenever the offsetbands
    change
    
    if None, no weighting will be done.  otherwise, offsetweights
    must be a sequence of length equal to offsetbands.  positibe
    values will be interpreted as raw scalings (i.e. offset=w*(dat-fid) )
    and negative values will be compared to the total range (i.e. 
    offset=-w*(dat-fid)/(max-min) )
    """)
    def _getLocW(self):
        if self._locw is None:
            return 0
        return self._locw
    
    def _setLocW(self,val):
        self._locw = val
        self._offsets = None
    locweight = property(_getLocW,_setLocW,doc="""
    Weights to apply to the location while calculating the offset. 
    """)
    
    
    def plot(self,bx,by,clf=True,skwargs={},lkwargs={}):
        """
        this plots the two bands specified by bx and by
        
        clf determines if the figure should be cleared before plotting
        
        skwargs are passed into pylab.scatter and lkwargs are passed
        into pylab.plot
        """
        from matplotlib import pyplot as plt
            
        fx,fy = self.getFiducialData(bx),self.getFiducialData(by)
        dx,dy = self.getData(bx),self.getData(by)
        
        if clf:
            plt.clf()
        
        if 'c' not in skwargs:
            skwargs['c'] = 'b'
        if 'c' not in lkwargs:
            skwargs['c'] = 'r'
        plt.scatter(dx,dy,**skwargs)
        plt.plot(fx,fy,**lkwargs)
        
        if isinstance(bx,int):
            bx = self._bandnames[bx]
        if isinstance(by,int):
            by = self._bandnames[by]
        
        plt.xlabel(bx)
        plt.ylabel(by)
        
        if '-' not in bx:
            plt.xlim(*reversed(plt.xlim()))
        if '-' not in by:
            plt.ylim(*reversed(plt.ylim()))
        
    
def _CMDtest(nf=100,nd=100,xA=0.3,yA=0.2,plot=False):
    from matplotlib import pyplot as plt
    x=np.linspace(0,1,nf)
    y=5-(x*2)**2+24
    x=x*0.6+.15
    
    fdi = (np.random.rand(nd)*nf).astype(int)
    dx = x[fdi]+xA*(2*np.random.rand(nd)-1)
    dy = y[fdi]+yA*np.random.randn(nd)
    if plot:
        plt.clf()
        plt.plot(x,y,c='r')
        plt.scatter(dx,dy)
        plt.ylim(*reversed(plt.ylim()))
        
    cmda = CMDAnalyzer((x,y),('g-r','r'),{'a':np.arange(50),'b':np.arange(50)+50})
    cmda.setData({'g-r':dx,'r':dy})
    cmda.center = (10,10)
    cmda.locs = np.random.randn(2,nd)/10+cmda.center[0]
    cmda.offsetbands=['g-r','r']
        
    return x,y,dx,dy,cmda



class AperturePhotometry(object):
    """
    This class generates radial surface brightness profiles from
    various sources and provides plotting and fitting of those 
    profiles   
    
    specifying a Band results in use of that band's zero point
    
    apertures can be a positive number to specify a fixed number of
    apertures, a negative number specifying the spacing between
    apertures in the specified units, or a sequence for fixed 
    aperture sizes in the specified units
    #TODO:TEST!
    """
    def __init__(self,band = None,units='arcsec',apertures=10,usemags=True,circular=True):
        self.circular = circular
        self.usemags = usemags
        self.apertures = apertures
        
        self.band = band
        self.units = units
        
        
    def _getUnit(self):
        return self._sunit
    def _setUnit(self,unit):
        if unit == 'arcsec':
            self._sunit = 'arcsec'
            self._unitconv = 1
        elif unit == 'radians' or unit == 'sterradians' or unit == 'sr':
            self._sunit = 'radians'
            self._unitconv = 60*60*360/2/pi
        elif 'deg' in unit:
            self._sunit = 'degrees'
            self._unitconv = 60*60
        else:
            raise ValueError('unrecognized unit')
    units = property(_getUnit,_setUnit)
    
    def _getBand(self):
        return self._band
    def _setBand(self,band):
        if isinstance(band,basestring):
            global bands
            self._band = bands[band]
        elif isinstance(band,Band):
            self._band = band
        elif band is None:
            self._band = None
        else:
            raise ValueError("input band was not a Band or registered band name")
    band = property(_getBand,_setBand)
        
    def _magorfluxToFlux(self,magorflux):
        if self.usemags:
            zptf = 0 if (self._band is None) else self.band.zptflux
            flux = zptf*_mag_to_flux(magorflux)
        else:
            flux = magorflux
        return flux 
    
    def _outFluxConv(self,flux):
        """
        convert flux back into mags if necessary and set zero-points appropriately
        """
        if self.usemags:
            zptf = 0 if (self._band is None) else self.band.zptflux
            out = _flux_to_mag(flux/zptf)
        else:
            out = flux
        return out
    
    def _fitPhot(self,x,y,flux,cen,aps=''):
        """
        input x,y,cen should be in un-converted units
        """        
        if not self.circular:
            raise NotImplementedError('elliptical fitting not supported yet')
        r = np.sum((np.array((x,y),copy=False).T-cen)**2,axis=1)**0.5
        
        if np.isscalar(self.apertures):
            if self.apertures<0:
                rap = np.arange(0,np.max(r),self.apertures)+self.apertures
            else:
                rap = np.linspace(0,np.max(r),self.apertures+1)[1:]
        else:    
            rap = np.array(self.apertures)
            
        r,rap = self._unitconv*r,self._unitconv*rap
        
        apmask = r.reshape((1,r.size)) <= rap.reshape((rap.size,1)) #new shape (rap.size,r.size)
        fluxap = np.sum(apmask*flux,axis=1)
        fluxann = fluxap-np.roll(fluxap,1)
        fluxann[0] = fluxap[0] 
        A = pi*rap*rap
        A = A - np.roll(A,1)
        A[0] = pi*rap[0]**2
        sbap = fluxann/A
        #TODO:better/correct SB?
        
#        valid = sbap > 0
#        self.enclosed = self._outFluxConv(fluxap[valid])
#        self.mu = self._outFluxConv(sbap[valid])
#        self.rap = rap   [valid]

        highest = np.min(np.where(np.concatenate((sbap,(0,)))<=0))
        self.enclosed = self._outFluxConv(fluxap[:highest])
        self.mu = self._outFluxConv(sbap[:highest])
        self.rap = rap[:highest]/self._unitconv
        
    def pointSourcePhotometry(self,x,y,magorflux,cen='centroid'):
        """
        x,y,and magorflux are arrays of matching shape 
        
        cen is 'centroid' to use tjhe raw centroid, 'weighted' to weight the
        centroid by the flux, or a 2-sequence to manually assign a center
        """
        x = np.array(x,copy=False)
        y = np.array(x,copy=False)
        flux = self._magorfluxToFlux(np.array(magorflux,copy=False))
        
        if x.shape != y.shape != flux.shape:
            raise ValueError("shapes don't match!")
        
        if isinstance(cen,basestring):
            if cen == 'centroid':
                cen = np.array((np.average(x),np.average(y)))
            elif cen == 'weighted':
                cen = np.array((np.average(x,weights=flux),np.average(y,weights=flux)))
            else:
                raise ValueError('unrecognized cen string')
        else:
            cen = np.array(cen,copy=False)
            if cen.shape != (2,):
                raise ValueError('cen not a 2-sequence')
        
        return self._fitPhot(x,y,flux,cen)
    
    def imagePhotometry(self,input,platescale):
        """
        input must be a 2D array or a CCD
        
        platescale is linear units as specified by the units property per pixel
        """
        from .ccd import CCDImage
        
        if isinstance(input,CCDImage):
            raise NotImplementedError
        
        magorflux = np.array(input,copy=True)
        if len(magorflux.shape) != 2:
            raise ValueError('input not 2D')
        flux = self._magorfluxToFlux(magorflux)
        
        
        raise NotImplementedError
        return self._fitPhot(x,y,flux,cen)
    
    def plot(self,fmt='o-',logx=False,**kwargs):
        """
        plot the surface brightness profile (must be generated)
        using matplotlib
        
        kwargs go into matplotlib.plot
        """
        
        from matplotlib import pyplot as plt
        if logx:
            plt.semilogx()
        if 'fmt':

            plt.plot(self.rap,self.mu,fmt,**kwargs)
        
        plt.ylim(*reversed(plt.ylim()))
        
        plt.xlabel('$r \\, [{\\rm arcsec}]$')
        if self.band is None:
            plt.ylabel('$\\mu$')
        else:
            plt.ylabel('$\\mu_{%s}$'%self.band.name)
            
        
        
#<------------------------conversion functions--------------------------------->
    
def UBVRI_to_ugriz(U,B,V,R,I,ugrizprimed=False):
    """
    transform UBVRcIc magnitudes to ugriz magnitudes as per Jester et al. (2005)
    """
    if not ugrizprimed:
        umg    =    1.28*(U-B)   + 1.13  
        #gmr    =    1.02*(B-V)   - 0.22  
        rmi    =    0.91*(R-I) - 0.20 
        rmz    =    1.72*(R-I) - 0.41
        g      =    V + 0.60*(B-V) - 0.12 
        r      =    V - 0.42*(B-V) + 0.11
        

    else:
        raise NotImplementedError
    
    return umg+g,g,r,r-rmi,r-rmz
    
def ugriz_to_UBVRI(u,g,r,i,z,ugrizprimed=False):
    """
    transform ugriz magnitudes to UBVRcIc magnitudes as per Jester et al. (2005)
    (note that z is unused)
    """
    if not ugrizprimed:
        UmB    =    0.78*(u-g) - 0.88 
        #BmV    =    0.98*(g-r) + 0.22 
        VmR    =    1.09*(r-i) + 0.22
        RmI  =    1.00*(r-i) + 0.21
        B      =    g + 0.39*(g-r) + 0.21
        V      =    g - 0.59*(g-r) - 0.01 

    else:
        raise NotImplementedError
    
    return UmB+B,B,V,V-VmR,V-VmR-RmI

def transform_dict_ugriz_UBVRI(d,ugrizprimed=False):
    ugriz = 'u' in d or 'g' in d or 'r' in d or 'i' in d or 'z' in d
    UBVRI = 'U' in d or 'B' in d or 'V' in d or 'R' in d or 'I' in d
    if ugriz and UBVRI:
        raise ValueError('both systems already present')
    if ugriz:
        u=d['u'] if 'u' in d else 0
        g=d['g'] if 'g' in d else 0
        r=d['r'] if 'r' in d else 0
        i=d['i'] if 'i' in d else 0
        z=d['z'] if 'z' in d else 0
        U,B,V,R,I=ugriz_to_UBVRI(u,g,r,i,z,ugrizprimed)
        if 'g' in d and 'r' in d:
            d['B']=B
            d['V']=V
            if 'u' in d:
                d['U']=U
            if 'i' in d and 'z' in d:
                d['I']=I
                d['R']=R
        else:
            raise ValueError('need g and r to do anything')
        
    if UBVRI:
        U=d['U'] if 'U' in d else 0
        B=d['B'] if 'B' in d else 0
        V=d['V'] if 'V' in d else 0
        R=d['R'] if 'R' in d else 0
        I=d['I'] if 'I' in d else 0
        u,g,r,i,z=UBVRI_to_ugriz(U,B,V,R,I,ugrizprimed)
        if 'B' in d and 'V' in d:
            d['g']=g
            d['r']=r
            if 'U' in d:
                d['u']=u
            if 'R' in d and 'I' in d:
                d['i']=i
                d['z']=z
        else:
            raise ValueError('need B and V to do anything')

def M_star_from_mags(B,V,R,I,color='B-V'):
    """
    uses Bell&DeJong 01 relations
    color can either be a 'B-V','B-R','V-I', or 'mean'
    returns stellar mass as mean,(B-derived,V-derived,R-derived,I-derived)
    """    
    if color=='B-V':
        c=B-V
        mlrb=10**(-0.994+1.804*c)
        mlrv=10**(-0.734+1.404*c)
        mlrr=10**(-0.660+1.222*c)
        mlri=10**(-0.627+1.075*c)
    elif color=='B-R':
        c=B-R
        mlrb=10**(-1.224+1.251*c)
        mlrv=10**(-0.916+0.976*c)
        mlrr=10**(-0.820+0.851*c)
        mlri=10**(-0.768+0.748*c)
    elif color=='V-I':
        c=V-I
        mlrb=10**(-1.919+2.214*c)
        mlrv=10**(-1.476+1.747*c)
        mlrr=10**(-1.314+1.528*c)
        mlri=10**(-1.204+1.347*c)
    elif color=='mean':
        bv=M_star_from_mags(B,V,R,I,'B-V')
        br=M_star_from_mags(B,V,R,I,'B-R')
        vi=M_star_from_mags(B,V,R,I,'V-I')
        return np.mean((bv[0],br[0],vi[0])),np.mean((bv[1],br[1],vi[1]),axis=0)
    else:
        raise ValueError('Unknown color')
    
    mstar=[]
    mstar.append(mag_to_lum(B,'B')*mlrb)
    mstar.append(mag_to_lum(V,'V')*mlrv)
    mstar.append(mag_to_lum(R,'R')*mlrr)
    mstar.append(mag_to_lum(I,'I')*mlri)
    
    return np.mean(mstar),tuple(mstar)


def distance_modulus(x,intype='distance',dx=None,autocosmo=True):
    """
    compute the distance modulus given  a distance or redshift
    
    for H=0/False/None, will treat z as a distance in pc, otherwise, redshift
    will be used with hubble relation
    
    autocosmo determines if the cosmological calculation should be
    automatically performed for z > 0.1 . if False, the only the basic
    calculation will be done.  if 'warn,' a warning will be issued
    """
    from .coords import cosmo_z_to_dist
    from .constants import H0,c
    
    c=c/1e5 #km/s
    cosmo=False
    
    if intype == 'distance':
        z=x/1e6*H0/c
        if dx is not None:
            dz = dx/1e6*H0/c
        else:
            dz = None
    elif intype == 'redshift':
        z=x
        x=z*c/H0
        if dx is not None:
            dz = dx
            dx = dz*c/H0
        else:
            dz = None
    else:
        raise ValueError('unrecognized intype')
    
    if autocosmo and np.any(z) > 0.1:
        if autocosmo == 'warn':
            from warnings import warn
            warn('redshift < 0.1 - cosmological calculation should be used')
        else:
            cosmo=True
    if cosmo:
        return cosmo_z_to_dist(z,dz,4)
    elif dx is None:
        return 5*np.log10(x)-5
    else:
        dm = 5*np.log10(x)-5
        ddm = 5*dx/x/np.log(10)
        return dm,ddm,ddm
    
def distance_from_modulus(dm):
    """
    compute the distance given the specified distance modulus.  Currently
    non-cosmological
    """
    return 10**(1+dm/5.0)
    

def abs_mag(appmag,x,intype='distance',autocosmo=True):
    """
    computes absolute magnitude from apparent magnitude and distance.
    See astro.phot.distance_modulus for details on arguments
    """
    from operator import isSequenceType
    if isSequenceType(appmag):
        appmag=np.array(appmag)
    
    distmod = distance_modulus(x,intype,None,autocosmo)
    return appmag-distmod

def app_mag(absmag,x,intype='distance',autocosmo=True):
    """
    computes apparent magnitude from absolute magnitude and distance.
    See astro.phot.distance_modulus for details on arguments
    """
    from operator import isSequenceType
    if isSequenceType(absmag):
        absmag=np.array(absmag)
        
    distmod = distance_modulus(x,intype,None,autocosmo)
    return absmag+distmod

def rh_to_surface_brightness(totalm,rh):
    """
    Compute the surface brightness given a half-light radius in arcsec.  Note
    that the totalm is the integrated magnitude, not just the half-light
    """
    return area_to_surface_brightness(totalm+2.5*np.log10(2),pi*rh*rh)

def area_to_surface_brightness(m,area):
    """
    Compute the surface brightness given a particular magnitude and area in 
    mag/sq arc seconds
    """
    return m+2.5*np.log10(area)

def intensity_to_flux(radius,distance):
    """
    this converts a specific intensity measurement to a flux assuming 
    the source is a sphere of a specified radius at a specified
    distance (in the same units)
    """
    ratio=radius/distance
    return pi*ratio*ratio

def flux_to_intensity(radius,distance):
    """
    this converts a flux measurement to a specific intensity assuming 
    the source is a sphere of a specified radius at a specified
    distance (in the same units)
    """
    ratio=radius/distance
    return 1.0/(pi*ratio*ratio)

##Bell&DeJong & Blanton 03
#_band_to_msun={'B':5.47,
#               'V':4.82,
#               'R':4.46,
#               'I':4.14,
#               'K':3.33,
#               'u':6.80,
#               'g':5.45,
#               'r':4.76,
#               'i':4.58,
#               'z':4.51}

#B&M and http://www.ucolick.org/~cnaw/sun.html
_band_to_msun={'U':5.61,
               'B':5.48,
               'V':4.83,
               'R':4.42,
               'I':4.08,
               'J':3.64,
               'H':3.32,
               'K':3.28,
               'u':6.75,
               'g':5.33,
               'r':4.67,
               'i':4.48,
               'z':4.42}
               
def mag_to_lum(M,Mzpt=4.83,Lzpt=1,Merr=None):
    """
    calculate a luminosity from a magnitude
    
    input M can be either a magnitude value, a sequence/array of magnitudes, or
    a dictionary where the keys will be interpreted as specifying the bands  
    (e.g. they can be 'U','B','V', etc. to be looked up as described 
    below or a value for the zero-point)
    
    if Merr is given, will return (L,dL)
    
    Mzpt specifies the magnitude that matches Lzpt, so Lzpt is a unit conversion
    factor for luminosity - e.g. 4.64e32 for ergs in V with solar zero points,
    or 1 for solar
    
    Mzpt can also be 'U','B','V','R','I','J','H', or 'K' and will use B&M values 
    for solar magnitudes or 'u','g','r','i', or 'z' from http://www.ucolick.org/~cnaw/sun.html
    """
    from operator import isMappingType,isSequenceType
    
    dictin = isMappingType(M)    
    if dictin:
        dkeys = Mzpt = M.keys()
        M = M.values()
    elif type(M) is not np.ndarray:
        M=np.array(M)
        
    if isinstance(Mzpt,basestring):
        Mzpt=_band_to_msun[Mzpt]
    elif isSequenceType(Mzpt):    
        Mzpt=np.array(map(lambda x:_band_to_msun.get(x,x),Mzpt))
        
    #L=(10**((Mzpt-M)/2.5))*Lzpt
    L = _mag_to_flux(M-Mzpt)*Lzpt
    
    if dictin:
        L = dict([t for t in zip(dkeys,L)])
    
    if np.any(Merr):
        #dL=Merr*L/1.0857362047581294 #-1.0857362047581294 = -2.5/ln(10)
        dL = _magerr_to_fluxerr(Merr,M)
        return L,dL
    else:
        return L

def lum_to_mag(L,Mzpt=4.83,Lzpt=1,Lerr=None):
    """
    calculate a magnitude from a luminosity
    
    see mag_to_lum() for syntax details
    """
    from operator import isMappingType,isSequenceType
        
    dictin = isMappingType(L)    
    if dictin:
        dkeys = Mzpt = L.keys()
        L = L.values()
    elif type(L) is not np.ndarray:
        L=np.array(L)     
        
    if isinstance(Mzpt,basestring):
        Mzpt=_band_to_msun[Mzpt]
    elif isSequenceType(Mzpt):    
        Mzpt=np.array(map(lambda x:_band_to_msun.get(x,x),Mzpt))
        
    #M=Mzpt-2.5*np.log10(L/Lzpt)
    M = Mzpt+_flux_to_mag(L/Lzpt)

    if dictin:
        M = dict([t for t in zip(dkeys,M)])

    if np.any(Lerr):
        #dM=1.0857362047581294*Lerr/L #-1.0857362047581294 = -2.5/ln(10)
        dM = _fluxerr_to_magerr(Lerr,L)
        return M,dM
    else:
        return M
    
def intensities_to_sig(Is,In,exposure=1,area=1):
    """
    converts photon count intensities (i.e. photon cm^-2 sr^-1) to signficance
    values from poisson statistics.
    
    Is is intensity of the signal
    In is intensity of the background
    """
    return exposure*area*Is*(exposure*area*(Is+In))**-0.5
    
def cosmo_surface_brightness_correction(Sobs,z,mag=True):
    """
    computes
    
    mag determines if mag/as^2 is used or if False, flux
    """
    if mag:
        return Sobs-10*np.log10(1+z)
    else:
        return Sobs*(1+z)**4
    
def kcorrect(mags,zs,magerr=None,filterlist=['U','B','V','R','I']):
    """
    Uses the Blanton et al. 2003 k-correction
    
    requires pidly (http://astronomy.sussex.ac.uk/~anthonys/pidly/) and IDL with
    kcorrect installed
    
    input magnitudes should be of dimension (nfilter,nobj), as should magerr
    zs should be sequence of length nobj
    if magerr is None, 
    
    returns absmag,kcorrections,chi2s
    """
    from .constants import H0
    import pidly
    idl=pidly.IDL()
    idl('.com kcorrect')
    #TODO: figure out if it worked
    
    mags = np.array(mags,copy=False)
    zs = np.array(zs,copy=False).ravel()
    if magerr is None:
        magerr = np.ones_like(mags)
    else:
        magerr = np.array(magerr,copy=False)
    
    if mags.shape[0] != len(filterlist) or magerr.shape[0] != len(filterlist):
        raise ValueError("number of filters and magnitude shapes don't match")
    if mags.shape[1] != zs.size or magerr.shape[1] != zs.size:
        raise ValueError("number of redshifts doesn't match magnitude shapes")
        
    fd = {'U':'bessell_U.par',
          'B':'bessell_B.par',
          'V':'bessell_V.par',
          'R':'bessell_R.par',
          'I':'bessell_I.par',
          'u':'sdss_u0.par',
          'g':'sdss_g0.par',
          'r':'sdss_r0.par',
          'i':'sdss_i0.par',
          'z':'sdss_z0.par'}    
    
    filterlist = [fd.get(fl,fl) for fl in filterlist]
    
    try:
        idl.mags = mags
        idl.magerr = magerr
        idl.zs = zs
        idl.flst = filterlist
        idl('kcorrect,mags,magerr,zs,kcorr,absmag=absmag,chi2=chi2,filterlist=flst,/magnitude,/stddev')
        #idl.pro('kcorrect',mags,magerr,zs,'kcorr',absmag='absmag',chi2='chi2',filterlist=filterlist,magnitude=True,stddev=True,)
        
        kcorr = idl.kcorr
        absmag = idl.absmag +5*np.log10(H0/100)
        chi2 = idl.chi2    
        
        return absmag,kcorr,chi2
        
    finally:
        idl.close()
        
    
        
    
#<---------------------Load built-in data-------------------------------------->
class _BandRegistry(dict):
    def __init__(self):
        dict.__init__(self)
        self._groupdict = {}
        
    def __getitem__(self,val):
        if val in self._groupdict:
            bands = self._groupdict[val]
            return dict([(b,self[b]) for b in bands])
        else:
            return dict.__getitem__(self,val)
    def __delitem__(self,key):
        dict.__delitem__(key)
        for k,v in self._groupdict.items():
            if key in v:
                del self.groupdict[k]
                
    def __getattr__(self,name):
        if name in self.keys():
            return self[name]
        else:
            raise AttributeError('No band or attribute '+name+' in '+self.__class__.__name__)
    
    def register(self,bands,groupname=None):
        """
        register a set of bands in a group
        
        bands is a dictionary mapping the band name to a Band object
        
        setname is the name of the group to apply to the dictionary
        """
        from operator import isMappingType,isSequenceType
        
        if not isMappingType(bands):
            raise ValueError('input must be a map of bands')
        for k,v in bands.iteritems():
            if not isinstance(v,Band):
                raise ValueError('an object in the band set is not a Band')
            self[str(k)]=v
            
        if groupname:
            if type(groupname) is str:
                self._groupdict[groupname] = bands.keys()
            elif isSequenceType(groupname):
                for s in groupname:
                    self._groupdict[s] = bands.keys()
            else:
                raise ValueError('unrecognized group name type')
            
    def groupnames(self):
        return self._groupdict.keys()
    
    def groupiteritems(self):
        for k in self.groupkeys():
            yield (k,self[k])
            
def str_to_bands(bnds,forceregistry=False):
    """
    this translates a string or sequence of strings into a sequence of Band
    objects using the phot.bands band registry
    
    if forceregistry is True, new bands will not be accepted if they are not in the registry
    """
    from operator import isMappingType,isSequenceType
    global bands
    
    if isinstance(bnds,basestring):
        if bnds.lower() == 'all':
            bnds = bands.values()
        elif ',' in bnds:
            bnds = [bands[b.strip()] for b in bnds.split(',')]
        elif bnds in bands:
            bnds = bands[bnds]
            if isMappingType(bnds):
                bnds = bnds.values()
            else:
                bnds = (bnds,)
        else: #assume each charater is a band name
            bnds = [bands[b] for b in bnds.strip()]
            
    elif isSequenceType(bnds):
        bnds = [bands[b] if isinstance(b,basestring) else b for b in bnds] 
    elif isinstance(bnds,Band):
        if forceregistry and bnds.name not in bands:
            raise KeyError('requested band not in registry') 
        bnds = (Band,)
    else:
        raise KeyError('unrecognized band(s)')
    
    return bnds
#TODO: check UBVRI/ugriz S function - energy or quantal?

def __load_UBVRI():
    from .io import _get_package_data
    bandlines = _get_package_data('UBVRIbands.dat').split('\n')
    
    src = bandlines.pop(0).replace('#Source:','').strip()
    bandlines.pop(0)
    
    d={}
    for ln in bandlines:
        if ln.strip() == '':
            pass
        elif 'Band' in ln:
            k = ln.replace('Band','').strip()
            xl = []
            Rl = []
            d[k]=(xl,Rl)
        else:
            t = ln.split()
            xl.append(t[0])
            Rl.append(t[1])
            
    d = dict([(k,ArrayBand(np.array(v[0],dtype='f8'),np.array(v[1],dtype='f8'),name=k)) for k,v in d.iteritems()])
    for v in d.itervalues():
        v.source = src
    return d

def __load_JHK():
    from .io import _get_package_data
    bandlines = _get_package_data('JHKbands.dat').split('\n')
    
    src = bandlines.pop(0).replace('#2MASS J,H, and K bands:','').strip()
    
    d={}
    for ln in bandlines:
        if ln.strip() == '':
            pass
        elif 'Band' in ln:
            k = ln.replace('Band','').strip()
            xl = []
            Rl = []
            d[k]=(xl,Rl)
        else:
            t = ln.split()
            xl.append(t[0])
            Rl.append(t[1])
            
    d = dict([(k,ArrayBand(np.array(v[0],dtype='f8'),np.array(v[1],dtype='f8'),name=k,unit='microns')) for k,v in d.iteritems()])
    for v in d.itervalues():
        v.source = src
    return d

def __load_ugriz():
    from .io import _get_package_data
    bandlines = _get_package_data('ugrizbands.dat').split('\n')
    
    bandlines.pop(0)
    psrc = bandlines.pop(0).replace('#primes:','').strip()
    src = bandlines.pop(0).replace('#SDSS ugriz:','').strip()
    bandlines.pop(0)
    
    d={}
    for ln in bandlines:
        if ln.strip() == '':
            pass
        elif 'Band' in ln:
            k = ln.replace('Band','').strip()
            xl = []
            Rl = []
            d[k]=(xl,Rl)
        else:
            t = ln.split()
            xl.append(t[0])
            Rl.append(t[1])
            
    d = dict([(k,ArrayBand(np.array(v[0],dtype='f8'),np.array(v[1],dtype='f8'),name=k)) for k,v in d.iteritems()])
    for k,v in d.iteritems():
        if "'" in k:
            v.source = psrc
        else:
            v.source = src
    dp = {}
    for k in d.keys():
        if "'" in k: 
            dp[k]=d.pop(k)
    return d,dp

def __load_human_eye():
    from .io import _get_package_data
    bandlines = _get_package_data('eyeresponse.dat').split('\n')
    
    src = bandlines.pop(0).replace('#from','').strip()
    d={'cone_s':[],'cone_m':[],'cone_l':[]}
    for ln in bandlines:
        if ln.strip() == '':
            pass
        else:
            t = ln.strip().split(',')
            d['cone_l'].append((t[0],t[1]))
            d['cone_m'].append((t[0],t[2]))
            if t[3]!='':
                d['cone_s'].append((t[0],t[3]))
                
    
    d = dict([(k,np.array(v,dtype='f8')) for k,v in d.iteritems()])
    #logarithmic response data - must do 10**data, also, convert x-axis to angstroms
    d = dict([(k,ArrayBand(10*v[:,0],10**v[:,1],name=k)) for k,v in d.iteritems()])
    for v in d.itervalues():
        v.source = src
    return d


#register all the built-in bands
bands = _BandRegistry()
bands.register(__load_human_eye(),'eye')
d,dp = __load_ugriz()
bands.register(d,'ugriz')
bands.register(dp,'ugriz_prime')
del d,dp
bands.register(__load_UBVRI(),['UBVRI','UBVRcIc'])
bands.register(__load_JHK(),'JHK')
#default all to AB mags
set_zeropoint_system('AB','all')

#set the Spectrum eye sensitivity assuming a T=5800 blackbody
from .spec import Spectrum
def __generateRGBSensTuple():
        from .models import BlackbodyModel
        from .phot import bands

        x=np.linspace(3000,9000,1024)
        bm = BlackbodyModel(T=5800)
        spec = Spectrum(x,bm(x))
        eyefluxes = np.array(spec.rgbEyeColor())
        return tuple(eyefluxes)
Spectrum._rgbsensitivity = __generateRGBSensTuple()


class _BwlAdapter(dict): 
    def __getitem__(self,key):
        if key not in self:
            return bands[key].cen
        return dict.__getitem__(self,key)
bandwl = _BwlAdapter()
#photometric band centers - B&M ... deprecated, use bands[band].cen instead
bandwl.update({'U':3650,'B':4450,'V':5510,'R':6580,'I':8060,'u':3520,'g':4800,'r':6250,'i':7690,'z':9110})

del ABCMeta,abstractmethod,abstractproperty,Spectrum,pi,division #clean up namespace