import scurve
from SimPEG import np, sp, Utils, Solver
import matplotlib.pyplot as plt
import matplotlib

class Tree(object):
    def __init__(self, h_in, levels=3):
        assert type(h_in) is list, 'h_in must be a list'
        assert len(h_in) > 1, "len(h_in) must be greater than 1"

        h = range(len(h_in))
        for i, h_i in enumerate(h_in):
            if type(h_i) in [int, long, float]:
                # This gives you something over the unit cube.
                h_i = np.ones(int(h_i))/int(h_i)
            assert isinstance(h_i, np.ndarray), ("h[%i] is not a numpy array." % i)
            assert len(h_i.shape) == 1, ("h[%i] must be a 1D numpy array." % i)
            assert len(h_i) == 2**levels, "must make h and levels match"
            h[i] = h_i[:] # make a copy.
        self.h = h


        self._levels = levels
        self._levelBits = int(np.ceil(np.sqrt(levels)))+1


        self._z = scurve.zorder.ZOrder(self.dim,20)
        self._treeInds = set()
        self._treeInds.add(0)

    @property
    def dim(self): return len(self.h)
    @property
    def levels(self): return self._levels

    @property
    def _sortedInds(self):
        if getattr(self, '__sortedInds', None) is None:
            self.__sortedInds = sorted(self._treeInds)
        return self.__sortedInds

    def _structureChange(self):
        deleteThese = ['__sortedInds', '_gridCC', '_gridFx']
        for p in deleteThese:
            if hasattr(self, p): delattr(self, p)

    def _index(self, pointer):
        assert len(pointer) is self.dim+1
        assert pointer[-1] <= self.levels
        x = self._z.index([p for p in pointer[:-1]]) # copy
        return (x << self._levelBits) + pointer[-1]

    def _pointer(self, index):
        assert type(index) in [int, long]
        n = index & (2**self._levelBits-1)
        p = self._z.point(index >> self._levelBits)
        return p + [n] #[p[1],p[0],p[2]]

    def refine(self, function=None, recursive=True, cells=None):

        cells = cells if cells is not None else sorted(self._treeInds)
        recurse = []
        for cell in cells:
            p = self._pointer(cell)
            do = function(self._cellC(cell)) > p[-1]
            if do:
                recurse += self._refineCell(cell)

        if recursive and len(recurse) > 0:
            self.refine(function=function, recursive=True, cells=recurse)
        return recurse


    def _refineCell(self, pointer):
        self._structureChange()
        pointer = self._asPointer(pointer)
        ind = self._asIndex(pointer)
        assert ind in self
        h = self._levelWidth(pointer[-1])/2 # halfWidth
        nL = pointer[-1] + 1 # new level
        add = lambda p:p[0]+p[1]
        added = []
        def addCell(p):
            i = self._index(p+[nL])
            self._treeInds.add(i)
            added.append(i)

        addCell(map(add, zip(pointer[:-1], [0,0,0][:self.dim])))
        addCell(map(add, zip(pointer[:-1], [h,0,0][:self.dim])))
        addCell(map(add, zip(pointer[:-1], [0,h,0][:self.dim])))
        addCell(map(add, zip(pointer[:-1], [h,h,0][:self.dim])))
        if self.dim == 3:
            addCell(map(add, zip(pointer[:-1], [0,0,h])))
            addCell(map(add, zip(pointer[:-1], [h,0,h])))
            addCell(map(add, zip(pointer[:-1], [0,h,h])))
            addCell(map(add, zip(pointer[:-1], [h,h,h])))
        self._treeInds.remove(ind)
        return added

    def _corsenCell(self, pointer):
        self._structureChange()
        raise Exception('Not yet implemented')

    def _asPointer(self, ind):
        if type(ind) in [int, long]:
            return self._pointer(ind)
        if type(ind) is list:
            return ind
        if isinstance(ind, np.ndarray):
            return ind.tolist()
        raise Exception

    def _asIndex(self, pointer):
        if type(pointer) in [int, long]:
            return pointer
        if type(pointer) is list:
            return self._index(pointer)
        raise Exception

    def _parentPointer(self, pointer):
        mod = self._levelWidth(pointer[-1]-1)
        return [p - (p % mod) for p in pointer[:-1]] + [pointer[-1]-1]

    def _levelWidth(self, level):
        return 2**(self.levels - level)

    def _isInsideMesh(self, pointer):
        inside = True
        for p in pointer[:-1]:
            inside = inside and p >= 0 and p < 2**self.levels
        return inside

    def _getNextCell(self, ind, direction=0, positive=True):
        """
            Returns a None, int, list, or nested list
            The int is the cell number.

        """
        pointer = self._asPointer(ind)

        step = (1 if positive else -1) * self._levelWidth(pointer[-1])
        nextCell = [p if ii is not direction else p + step for ii, p in enumerate(pointer)]
        if not self._isInsideMesh(nextCell): return None

        # it might be the same size as me?
        if nextCell in self: return self._index(nextCell)
        # it might be smaller than me?
        if nextCell[-1] + 1 <= self.levels: # if I am not the smallest.
            nextCell[-1] += 1
            if not positive:
                nextCell[direction] -= step/2 # Get the closer one
            if nextCell in self: # there is at least one

                hw = self._levelWidth(pointer[-1]) / 2
                nextCell = np.array([p if ii is not direction else p + (step/2 if positive else 0) for ii, p in enumerate(pointer)])

                if self.dim == 3: raise Exception
                if direction == 0: children = [0,0,1], [0,hw,1]
                if direction == 1: children = [0,0,1], [hw,0,1]
                nextCells = []
                for child in children:
                    nextCells.append(self._getNextCell(nextCell + child, direction=direction,positive=positive))
                return nextCells

        # it might be bigger than me?
        return self._getNextCell(self._parentPointer(pointer),
                direction=direction, positive=positive)

    def __contains__(self, v):
        if type(v) in [int, long]:
            return v in self._treeInds
        return self._index(v) in self._treeInds

    def plotGrid(self, ax=None, showIt=False):

        if ax is None:
            fig = plt.figure()
            ax = plt.subplot(111)
        else:
            assert isinstance(ax,matplotlib.axes.Axes), "ax must be an Axes!"
            fig = ax.figure

        for ind in self._sortedInds:
            p = self._asPointer(ind)
            n = self._cellN(p)
            h = self._cellH(p)
            x = [n[0]    , n[0] + h[0], n[0] + h[0], n[0]       , n[0]]
            y = [n[1]    , n[1]       , n[1] + h[1], n[1] + h[1], n[1]]
            ax.plot(x,y, 'b-')

        ax.plot(self.gridCC[[0,-1],0], self.gridCC[[0,-1],1], 'ro')
        ax.plot(self.gridCC[:,0], self.gridCC[:,1], 'r.')
        ax.plot(self.gridCC[:,0], self.gridCC[:,1], 'r:')

        ax.plot(self.gridFx[self._hangingFacesX,0], self.gridFx[self._hangingFacesX,1], 'gs', ms=10, mfc='none', mec='green')
        ax.plot(self.gridFx[:,0], self.gridFx[:,1], 'g>')
        ax.plot(self.gridFy[self._hangingFacesY,0], self.gridFy[self._hangingFacesY,1], 'gs', ms=10, mfc='none', mec='green')
        ax.plot(self.gridFy[:,0], self.gridFy[:,1], 'g^')

        if showIt:plt.show()

    def _cellN(self, p):
        p = self._asPointer(p)
        return [hi[:p[ii]].sum() for ii, hi in enumerate(self.h)]
    def _cellH(self, p):
        p = self._asPointer(p)
        w = self._levelWidth(p[-1])
        return [hi[p[ii]:p[ii]+w].sum() for ii, hi in enumerate(self.h)]
    def _cellC(self, p):
        return (np.array(self._cellH(p))/2.0 + self._cellN(p)).tolist()

    @property
    def gridCC(self):
        if getattr(self, '_gridCC', None) is None:
            self._gridCC = np.zeros((len(self._treeInds),self.dim))
            for ii, ind in enumerate(self._sortedInds):
                p = self._asPointer(ind)
                self._gridCC[ii, :] = self._cellC(p)
        return self._gridCC

    @property
    def gridFx(self):
        if getattr(self, '_gridFx', None) is None:
            self.number()
        return self._gridFx

    @property
    def gridFy(self):
        if getattr(self, '_gridFy', None) is None:
            self.number()
        return self._gridFy

    def _onSameLevel(self, i0, i1):
        p0 = self._asPointer(i0)
        p1 = self._asPointer(i1)
        return p0[-1] == p1[-1]


    def number(self):

        facesX, facesY = [], []
        hangingFacesX, hangingFacesY = [], []
        faceXCount, faceYCount = -1, -1
        fXm,fXp,fYm,fYp,fZm,fZp = range(6)
        area, vol = [], []

        def addXFace(count, p, positive=True):
            n = self._cellN(p)
            w = self._cellH(p)
            area.append(w[1] if self.dim == 2 else w[1]*w[2])
            facesX.append([n[0] + (w[0] if positive else 0), n[1] + w[1]/2.0])
            return count + 1
        def addYFace(count, p, positive=True):
            n = self._cellN(p)
            w = self._cellH(p)
            area.append(w[0] if self.dim == 2 else w[0]*w[2])
            facesY.append([n[0] + w[0]/2.0, n[1] + (w[1] if positive else 0)])
            return count + 1

        # c2cn = dict()
        c2f = dict()
        def gc2f(ind):
            if ind in c2f: return c2f[ind]
            c2f_ind = [list() for _ in xrange(2*self.dim)]
            c2f[ind] = c2f_ind
            return c2f_ind

        def processCell(ind, faceCount, addFace, hangingFaces, DIR=0):

            fM,fP=(0,1) if DIR == 0 else (2,3) if DIR == 1 else (4,5)
            p = self._asPointer(ind)
            if self._getNextCell(p, direction=DIR, positive=False) is None:
                faceCount = addFace(faceCount, p, positive=False)
                gc2f(ind)[fM] += [faceCount]

            nextCell = self._getNextCell(p, direction=DIR)

            # Add the next Xface
            if nextCell is None:
                # on the boundary
                faceCount = addFace(faceCount, p)
                gc2f(ind)[fP] += [faceCount]
            elif type(nextCell) in [int, long] and self._onSameLevel(p,nextCell):
                # same sized cell
                faceCount = addFace(faceCount, p)
                gc2f(ind)[fP]      += [faceCount]
                gc2f(nextCell)[fM] += [faceCount]
            elif type(nextCell) in [int, long] and not self._onSameLevel(p,nextCell):
                # the cell is bigger than me
                faceCount = addFace(faceCount, p)
                gc2f(ind)[fP]      += [faceCount]
                gc2f(nextCell)[fM] += [faceCount]
                hangingFaces.append(faceCount)
            elif type(nextCell) is list:
                # the cell is smaller than me

                # TODO: ensure that things are balanced.
                p0 = self._pointer(nextCell[0])
                p1 = self._pointer(nextCell[1])

                faceCount = addFace(faceCount, p0, positive=False)
                gc2f(nextCell[0])[fM] += [faceCount]
                faceCount = addFace(faceCount, p1, positive=False)
                gc2f(nextCell[1])[fM] += [faceCount]

                gc2f(ind)[fP] += [faceCount-1,faceCount]

                hangingFaces += [faceCount-1, faceCount]

            return faceCount

        for ii, ind in enumerate(self._sortedInds):
            # c2cn[ind] = ii
            vol.append(np.prod(self._cellH(ind)))
            faceXCount = processCell(ind, faceXCount, addXFace, hangingFacesX, DIR=0)
            faceYCount = processCell(ind, faceYCount, addYFace, hangingFacesY, DIR=1)

        self._c2f = c2f
        self.area = np.array(area)
        self.vol = np.array(vol)
        self._gridFx = np.array(facesX)
        self._gridFy = np.array(facesY)
        self.nC = len(self._sortedInds)
        self.nFx = self._gridFx.shape[0]
        self.nFy = self._gridFy.shape[0]
        self.nF = self.nFx + self.nFy
        self._hangingFacesX = hangingFacesX
        self._hangingFacesY = hangingFacesY

    @property
    def faceDiv(self):
        print self._c2f
        if getattr(self, '_faceDiv', None) is None:
            self.number()
            # TODO: Preallocate!
            I, J, V = [], [], []
            PM = [-1,1]*self.dim # plus / minus
            offset = [0,0,self.nFx,self.nFx]

            for ii, ind in enumerate(self._sortedInds):
                faces = self._c2f[ind]
                for off, pm, face in zip(offset,PM,faces):
                    j = [_ + off for _ in face]
                    I += [ii]*len(j)
                    J += j
                    V += [pm]*len(j)

            VOL = self.vol
            D = sp.csr_matrix((V,(I,J)), shape=(self.nC, self.nF))
            S = self.area
            self._faceDiv = Utils.sdiag(1.0/VOL)*D*Utils.sdiag(S)
        return self._faceDiv



if __name__ == '__main__':


    def function(xc):
        r = xc - np.r_[0.5,0.5]
        dist = np.sqrt(r.dot(r))
        # if dist < 0.05:
        #     return 5
        if dist < 0.1:
            return 4
        if dist < 0.3:
            return 3
        if dist < 1.0:
            return 2
        else:
            return 0

    # T = Tree([16,16],levels=4)
    # T.refine(function,recursive=True)
    # T.plotGrid(showIt=True)
    # BREAK
    T = Tree([np.r_[1,2,1,5,2,3,1,1],8])
    T._refineCell([0,0,0])
    T._refineCell([4,4,1])
    T._refineCell([0,0,1])
    T._refineCell([2,2,2])
    T.plotGrid(showIt=True)

    T.number()
    print sorted(T._treeInds) == [32, 40, 48, 60, 61, 62, 63, 68, 132, 224, 232, 240, 248]
    print len(T._hangingFacesX) == 7
    print T.nFx == 18
    print T.vol == 1.0
    print T.area

    T.faceDiv

    plt.subplot(211)
    plt.spy(T.faceDiv)
    T.plotGrid(ax=plt.subplot(212), showIt=True)

    print T._getNextCell([4,0,1]) is None
    print T._getNextCell([0,4,1]) == [T._index([4,4,2]), T._index([4,6,2])]
    print T._getNextCell([0,2,2]) == [T._index([2,2,3]), T._index([2,3,3])]
    print T._getNextCell([4,4,2]) == T._index([6,4,2])
    print T._getNextCell([6,4,2]) is None
    print T._getNextCell([2,0,2]) == T._index([4,0,1])
    print T._getNextCell([4,0,1], positive=False) == [T._index([2,0,2]), [T._index([3,2,3]), T._index([3,3,3])]]
    print T._getNextCell([3,3,3]) == T._index([4,0,1])
    print T._getNextCell([3,2,3]) == T._index([4,0,1])
    print T._getNextCell([2,2,3]) == T._index([3,2,3])
    print T._getNextCell([3,2,3], positive=False) == T._index([2,2,3])


    print T._getNextCell([0,0,2], direction=1) == T._index([0,2,2])
    print T._getNextCell([0,2,2], direction=1, positive=False) == T._index([0,0,2])
    print T._getNextCell([0,2,2], direction=1) == T._index([0,4,1])
    print T._getNextCell([0,4,1], direction=1, positive=False) ==  [T._index([0,2,2]), [T._index([2,3,3]), T._index([3,3,3])]]


