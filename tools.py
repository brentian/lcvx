"""
Helper functions.

D. Malyuta -- ACL, University of Washington
B. Acikmese -- ACL, University of Washington

Copyright 2019 University of Washington. All rights reserved.
"""

import sys
import numpy as np
import numpy.linalg as la
import scipy.linalg as sla
import cvxpy as cvx
import progressbar as progressbar

def golden(f,lb,ub,tol,name=None):
    """
    Golden search for a minimum.
    
    Parameters
    ----------
    f : function
        Oracle which returns status (e.g. of the optimization problem) and
        f(x). Must be unimodal \in [lb,ub].
    lb : float
        Search interval lower bound.
    ub : float
        Search interval upper bound.
    tol : float
        Convergence tolerance, such that the minimum is within tol units away
        from the returned x.
    name: str, optional
        Display a name for the progressbar.
    
    Returns
    -------
    x : float
        Minimum location, \in [lb,ub].
    solver_time : float
        Sum of solver times for all calls to the optimizer
    """
    # Maintains the interval [x1,(x2,x4),x3] where [x1,x3] brackets the
    # minimum and x2, x4 are intermediate points used to update the bracket
    solver_time = 0
    x = [lb,np.nan,ub]
    fx2 = np.nan
    phi = (1+np.sqrt(5))/2. # Golden ratio
    icount = np.ceil(np.log((ub-lb)/(2*tol))/np.log(phi)) if ub>lb else 0
    if icount == 0:
        x[1] = ub
    name = '' if name is None else name
    widgets=[name,'[%.2f,%.2f,%.2f]'%(x[0],np.nan,x[2]),' ',progressbar.Bar(),' (',
             progressbar.ETA(), ') (solver time: ','0.00',' s)']
    for i in progressbar.progressbar(range(int(icount)),widgets=widgets):
        try:
            if np.isnan(x[1]):
                x[1] = (phi*x[0]+x[2])/(phi+1.)
                _,fx2,time = f(x[1])
                solver_time += time
                widgets[-2] = '%.2e'%(solver_time)
            x4 = x[0]+x[2]-x[1]
            status,fx4,time = f(x4)
            solver_time += time
            if fx4<=fx2:
                x[0] = x[1]
                x[1] = x4
                fx2 = fx4
            else:
                x[2] = x[0]
                x[0] = x4
            y = np.sort(x)
            widgets[1] = '[%.2f,%.2f,%.2f] {%s}'%(y[0],y[1],y[2],status)
            widgets[-2] = '%.2e'%(solver_time)
        except KeyboardInterrupt:
            sys.exit()
    
    # Get the location that is feasible, starting from the upper bound
    y = np.sort(x)
    for i in range(2,-1,-1):
        status,_,time = f(y[i])
        solver_time += time
        if status=='optimal' or status=='optimal_inaccurate':
            x = y[i]
            break
    widgets[-2] = '%.2e'%(solver_time)
    
    return x,solver_time

def cost_profile(oracle,t_range):
    """
    Get the cost function profile.
    
    Parameters
    ----------
    oracle : callable
        Call signature cost=oracle(time) where time (float) is the final time
        and cost (float) is the optimal cost.
    t_range : list
        List of times to compute the cost at.
        
    Returns
    -------
    J : array
        Array of optimal cost values at those times.
    """
    J = np.array([oracle(t) for t in progressbar.progressbar(t_range)])
    return J

def discretize(Ac,Bc,dt):
    """Dynamics discretization"""
    M = sla.expm(np.block([[Ac,Bc],
                           [np.zeros([Bc.shape[1],
                                      Ac.shape[1]+Bc.shape[1]])]])*dt)
    A = M[:Ac.shape[0],:Ac.shape[0]]
    B = M[:Ac.shape[0],Ac.shape[0]:]
    return A,B

def cvx2arr(x,dual=False):
    """Convert CVX variable to an array"""
    return np.array(x.value.T if not dual else x.dual_value.T).flatten()

def project(y,C):
    """
    Project vector y onto the polytopic set {u: C*u<=0}.
    
    Parameters
    ----------
    y : array
        Vector to project.
    C : array
        Matrix whose rows are the polytopic set facet normals.
        
    Returns
    -------
    z : array
        Projection of y.
    """
    z = cvx.Variable(y.size)
    cost = cvx.Minimize(cvx.norm2(y-z))
    constraints = [C*z <= 0]
    problem = cvx.Problem(cost,constraints)
    problem.solve(solver=cvx.ECOS,verbose=False)
    if problem.status!='optimal' and problem.status!='optimal_inaccurate':
        raise RuntimeError('Projection operation failed')
    return cvx2arr(z)

def pbh(A,B):
    """
    Popov-Belevitch-Hautus controllability test for the pair {A,B}.
    
    Returns
    ----------
    : bool
        ``True`` if the pair {A,B} is controllable.
    """
    nx = A.shape[1]
    eigvals,eigvecs = la.eig(A)
    for eigval,eigvec in zip(eigvals,eigvecs):
        pbh_mat = np.column_stack([eigval*np.eye(A.shape[1])-A,B])
        if la.matrix_rank(pbh_mat)<nx:
            return False
    return True

def make_cone(alpha,roll,pitch,yaw,normal=False):
    """
    Generates a four-sided cone {u: C*u<=0} with opening angle alpha and
    pointed according to Tait-Bryan convention. The cone is rotated starting
    from a +z orientation.
    
    Parameters
    ----------
    alpha : float
        Cone opening angle (angle between two opposing hyperplanes) in degrees.
    roll : float
        Roll angle about x'' in degrees.
    pitch : float
        Pitch angle aboubt y' in degrees.
    yaw : float
        Yaw angle about z in degrees.
    normal : float
        Compute instead the normal cone to {u: C*u<=0}, i.e. the set
        {v: N*v<=0} such that v^T*u<=0 for all u such that C*u<=0.
    
    Returns
    -------
    C : array
        Matrix whose rows are the facet outwarding-facing normals (of the cone
        or of the normal cone).
    """
    alpha = np.deg2rad(alpha)
    roll = np.deg2rad(roll)
    pitch = np.deg2rad(pitch)
    yaw = np.deg2rad(yaw)
    c = lambda u: np.cos(u)
    s = lambda u: np.sin(u)
    Rx = lambda u: np.array([[1,0,0],[0,c(u),-s(u)],[0,s(u),c(u)]])
    Ry = lambda u: np.array([[c(u),0,s(u)],[0,1,0],[-s(u),0,c(u)]])
    Rz = lambda u: np.array([[c(u),-s(u),0],[s(u),c(u),0],[0,0,1]])
    # Compute the non-rotated cone
    angle = 0. if normal else np.pi/2.
    nhat_base = np.array([0,0,1])
    C_base = np.row_stack([Rx(angle+alpha/2.).dot(nhat_base),
                           Rx(-angle-alpha/2.).dot(nhat_base),
                           Ry(angle+alpha/2.).dot(nhat_base),
                           Ry(-angle-alpha/2.).dot(nhat_base),
                           -nhat_base])
    R = Rz(yaw).dot(Ry(pitch)).dot(Rx(roll)) # Overall active rotation
    C = C_base.dot(R.T)
    return C