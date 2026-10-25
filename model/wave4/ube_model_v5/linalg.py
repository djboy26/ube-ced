"""
linalg.py - the few pieces of linear algebra the v4 model needs, in plain Python
===============================================================================

Wave 2 used numpy.  v4 must run on the standard library alone, so this file
supplies exactly what the input-output model uses and no more:

  * an LU factorisation with partial pivoting (Gaussian elimination), so that
    one matrix is factorised once and then solved against many vectors;
  * the Leontief "multiplier" solve, m' = e' (I - A)^-1, done as the linear
    system (I - A)^T m = e, which never forms the inverse;
  * the "output" solve, x = (I - A)^-1 f;
  * matrix-vector products for the supply-chain tier expansion;
  * the spectral radius of a non-negative matrix by power iteration, which is
    the productivity check (a Leontief inverse exists and is non-negative
    exactly when the spectral radius of A is below 1).

The orientation convention is the programme's, stated once:
    A[i][j] = the amount of industry i's product used per unit of output of j.
Column j is the recipe for j.
"""

from __future__ import annotations


def lu_factor(M):
    """Doolittle LU with partial pivoting.  Returns (LU, perm)."""
    n = len(M)
    LU = [list(map(float, row)) for row in M]
    perm = list(range(n))
    for k in range(n):
        p = max(range(k, n), key=lambda i: abs(LU[i][k]))
        if LU[p][k] == 0.0:
            raise ZeroDivisionError("singular matrix")
        if p != k:
            LU[k], LU[p] = LU[p], LU[k]
            perm[k], perm[p] = perm[p], perm[k]
        rk = LU[k]
        akk = rk[k]
        for i in range(k + 1, n):
            ri = LU[i]
            f = ri[k] / akk
            ri[k] = f
            if f != 0.0:
                for j in range(k + 1, n):
                    ri[j] -= f * rk[j]
    return LU, perm


def lu_solve(fac, b):
    LU, perm = fac
    n = len(LU)
    y = [float(b[perm[i]]) for i in range(n)]
    for i in range(n):
        ri = LU[i]
        s = y[i]
        for j in range(i):
            s -= ri[j] * y[j]
        y[i] = s
    for i in range(n - 1, -1, -1):
        ri = LU[i]
        s = y[i]
        for j in range(i + 1, n):
            s -= ri[j] * y[j]
        y[i] = s / ri[i]
    return y


def identity_minus(A):
    n = len(A)
    return [[(1.0 if i == j else 0.0) - A[i][j] for j in range(n)] for i in range(n)]


def transpose(A):
    return [list(col) for col in zip(*A)]


def matvec(A, v):
    return [sum(a * b for a, b in zip(row, v)) for row in A]


def dot(u, v):
    return sum(a * b for a, b in zip(u, v))


class Leontief:
    """
    (I - A)^-1 without ever forming it.

    multiplier(e) returns m with m' = e' (I - A)^-1, i.e. the cumulative
    (direct plus all upstream) requirement per unit of each industry's output.
    output(f) returns x = (I - A)^-1 f, the total output needed to deliver f.
    """

    def __init__(self, A):
        self.A = A
        IA = identity_minus(A)
        self._fac_T = lu_factor(transpose(IA))
        self._fac = lu_factor(IA)

    def multiplier(self, e):
        return lu_solve(self._fac_T, e)

    def output(self, f):
        return lu_solve(self._fac, f)


def spectral_radius_nonneg(A, iters: int = 5000, tol: float = 1e-13) -> float:
    """Perron root of a non-negative matrix by power iteration."""
    n = len(A)
    v = [1.0 / n] * n
    lam = 0.0
    for _ in range(iters):
        w = matvec(A, v)
        s = sum(abs(t) for t in w)
        if s == 0.0:
            return 0.0
        w = [t / s for t in w]
        if abs(s - lam) < tol * max(1.0, s):
            return s
        lam, v = s, w
    return lam


def technical_coefficients(Z, x):
    """A[i][j] = Z[i][j] / x_j; a column with zero output is left at zero."""
    n = len(x)
    return [[(Z[i][j] / x[j] if x[j] > 0 else 0.0) for j in range(n)] for i in range(n)]


def orientation_worked_example() -> dict:
    """
    The two-sector proof of the A-matrix orientation, carried over from Wave 2.

    Steel (0) needs 0.5 Coal (1) per unit; Coal needs no Steel; Coal carries 1
    unit of direct energy, Steel none; final demand is 1 Steel.  The true
    answer is arithmetic: total output (1, 0.5), total energy 0.5.  With
    A[1][0] = 0.5 (row Coal, column Steel) the Leontief solve returns 0.5;
    the transpose returns 0 and loses the coal entirely.
    """
    A = [[0.0, 0.0], [0.5, 0.0]]
    f = [1.0, 0.0]
    e = [0.0, 1.0]
    x_ok = Leontief(A).output(f)
    x_bad = Leontief(transpose(A)).output(f)
    return {
        "convention": "A[i,j] = input from sector i per unit of output of sector j",
        "true_total_energy": 0.5,
        "energy_with_stated_convention": dot(e, x_ok),
        "energy_with_transpose": dot(e, x_bad),
        "output_with_stated_convention": x_ok,
        "output_with_transpose": x_bad,
        "passes": abs(dot(e, x_ok) - 0.5) < 1e-12 and abs(dot(e, x_bad)) < 1e-12,
    }
