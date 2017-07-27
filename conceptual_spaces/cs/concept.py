# -*- coding: utf-8 -*-
"""
Created on Tue Jun  6 11:54:30 2017

@author: lbechberger
"""

from math import exp, sqrt, factorial, pi, gamma, log, isnan
import itertools
import scipy.optimize

import core as cor
import cuboid as cub
import weights as wghts
import cs

class Concept:
    """A concept, implementation of the Fuzzy Simple Star-Shaped Set (FSSSS)."""
    
    def __init__(self, core, mu, c, weights):
        """Initializes the concept."""

        if (not isinstance(core, cor.Core)) or (not cor.check(core._cuboids, core._domains)):
            raise Exception("Invalid core")

        if mu > 1.0 or mu <= 0.0:
            raise Exception("Invalid mu")
        
        if c <= 0.0:
            raise Exception("Invalid c")
        
        if (not isinstance(weights, wghts.Weights)) or (not wghts.check(weights._domain_weights, weights._dimension_weights)):
            raise Exception("Invalid weights")
        
        self._core = core
        self._mu = mu
        self._c = c
        self._weights = weights
            
    def __str__(self):
        return "core: {0}\nmu: {1}\nc: {2}\nweights: {3}".format(self._core, self._mu, self._c, self._weights)
    
    def __eq__(self, other):
        if not isinstance(other, Concept):
            return False
        if not (self._core == other._core and cs.equal(self._mu, other._mu) and cs.equal(self._c, other._c) and self._weights == other._weights):
#        if self._core != other._core or self._mu != other._mu or self._c != other._c or self._weights != other._weights:
            return False
        return True
    
    def __ne__(self, other):
        return not self.__eq__(other)
    
    def membership_of(self, point):
        """Computes the membership of the point in this concept."""
        
        min_distance = reduce(min, map(lambda x: cs.distance(x, point, self._weights), self._core.find_closest_point_candidates(point)))
        
        return self._mu * exp(-self._c * min_distance)
    
    def _intersection_mu_special_case(self, a, c2, b, mu):
        """Membership of b in c2 (other) to c1 (self) is higher than mu (other)."""

        def makeFun(idx): # need this in order to avoid weird results (defining lambda in loop)
            return (lambda y: y[idx] - b[idx])
        distance = - log(mu / self._mu) / self._c
        y = []
        for i in range(cs._n_dim):
            if a[i] == b[i]:
                y.append(a[i])
            else:
                constr = [{"type":"eq", "fun":(lambda y: cs.distance(a,y,self._weights) - distance)}]
                for j in range(cs._n_dim):
                    if i != j:
                        constr.append({"type":"eq", "fun":makeFun(j)})
                
                if a[i] < b[i]:
                    opt = scipy.optimize.minimize(lambda y: -y[i], b, constraints = constr)
                    if not opt.success:
                        raise Exception("Optimizer failed!")
                    y.append(opt.x[i])
                else: 
                    opt = scipy.optimize.minimize(lambda y: y[i], b, constraints = constr)
                    if not opt.success:
                        raise Exception("Optimizer failed!")
                    y.append(opt.x[i])
        
        # arrange entries in b and y to make p_min and p_max; make sure we don't fall out of c2
        p_min = map(max, map(min, b, y), c2._p_min)
        p_max = map(min, map(max, b, y), c2._p_max)
        
        # take the unification of domains
        return p_min, p_max
    
    def _intersect_fuzzy_cuboids(self, c1, c2, other):
        """Find the highest intersection of the two cuboids (c1 from this, c2 from the other concept)."""
        
        crisp_intersection = c1.intersect_with(c2)
        if (crisp_intersection != None):  # crisp cuboids already intersect
            return min(self._mu, other._mu), crisp_intersection
        
        # already compute new set of domains
        new_domains = dict(c1._domains)
        new_domains.update(c2._domains)         
        
        # get ranges of closest points, store which dimensions need to be extruded, pick example points
        a_range, b_range = c1.get_closest_points(c2)
        a = map(lambda x: x[0], a_range)
        b = map(lambda x: x[0], b_range)
        extrude = map(lambda x: x[0] != x[1], a_range)
        
        mu = None
        p_min = None
        p_max = None
        if self._mu * exp(-self._c * cs.distance(a, b, self._weights)) >= other._mu:
            # intersection is part of other cuboid
            mu = other._mu
            p_min, p_max = self._intersection_mu_special_case(a, c2, b, mu)
        elif other._mu * exp(-other._c * cs.distance(a, b, other._weights)) >= self._mu:
            # intersection is part of this cuboid
            mu = self._mu
            p_min, p_max = other._intersection_mu_special_case(b, c1, a, mu)
        else:
            # intersection is in the cuboid between a and b
            # --> find point with highest identical membership to both cuboids
        
            # only use the relevant dimensions in order to make optimization easier
            def membership(x, point, mu, c, weights):
                x_new = []
                j = 0
                for dim in range(cs._n_dim):
                    if extrude[dim]:
                        x_new.append(point[dim])
                    else:
                        x_new.append(x[j])
                        j += 1
                return mu * exp(-c * cs.distance(point, x_new, weights))

            bounds = []
            for dim in range(cs._n_dim):
                if not extrude[dim]:
                    bounds.append((min(a[dim], b[dim]), max(a[dim], b[dim])))
            first_guess = map(lambda (x, y): (x + y)/2.0, bounds)
            to_minimize = lambda x: -membership(x, a, self._mu, self._c, self._weights)
            constr = [{"type":"eq", "fun":(lambda x: abs(membership(x, a, self._mu, self._c, self._weights) - membership(x, b, other._mu, other._c, other._weights)))}]
            opt = scipy.optimize.minimize(to_minimize, first_guess, constraints = constr, bounds = bounds, options = {"eps":cs._epsilon})
            if not opt.success:
                raise Exception("Optimizer failed!")
            # reconstruct full x by inserting fixed coordinates that will be extruded later
            x_star = []
            j = 0
            for dim in range(cs._n_dim):
                if extrude[dim]:
                    x_star.append(a[dim])
                else:
                    x_star.append(opt.x[j])
                    j += 1
            mu = membership(opt.x, a, self._mu, self._c, self._weights)

            # check if the weights are linearly dependent w.r.t. all relevant dimensions            
            relevant_dimensions = []
            for i in range(cs._n_dim):
                if not extrude[i]:
                    relevant_dimensions.append(i)
            relevant_domains = self._reduce_domains(cs._domains, relevant_dimensions)
            
            t = None
            weights_dependent = True
            for (dom, dims) in relevant_domains.items():
                for dim in dims:
                    if t is None:
                        # initialize
                        t = (self._weights._domain_weights[dom] * sqrt(self._weights._dimension_weights[dom][dim])) / (other._weights._domain_weights[dom] * sqrt(other._weights._dimension_weights[dom][dim]))
                    else:
                        # compare
                        t_prime = (self._weights._domain_weights[dom] * sqrt(self._weights._dimension_weights[dom][dim])) / (other._weights._domain_weights[dom] * sqrt(other._weights._dimension_weights[dom][dim]))
                        if round(t,10) != round(t_prime,10):
                            weights_dependent = False
                            break
                if not weights_dependent:
                    break
            
            if weights_dependent and len(relevant_domains.keys()) > 1:   
                # weights are linearly dependent and at least two domains are involved
                # --> need to find all possible corner points of resulting cuboid
                epsilon_1 = - log(mu / self._mu) / self._c
                epsilon_2 = - log(mu / other._mu) / other._c
                points = []
                
                for num_free_dims in range(1, len(relevant_dimensions)):
                    # start with a single free dimensions (i.e., edges of the bounding box) and increase until we find a solution
                    for free_dims in itertools.combinations(relevant_dimensions, num_free_dims):
                        # free_dims is the set of dimensions that are allowed to vary, all other ones are fixed
                        
                        binary_vecs = list(itertools.product([False,True], repeat = len(relevant_dimensions) - num_free_dims))
                        
                        for vec in binary_vecs:
                           
                            # compute the difference between the actual distance and the desired epsilon-distance
                            def epsilon_difference(x, point, weights, epsilon):
                                i = 0
                                j = 0
                                x_new = []
                                # puzzle together our large x vector based on the fixed and the free dimensions
                                for dim in range(cs._n_dim):
                                    if dim in free_dims:
                                        x_new.append(x[i])
                                        i += 1
                                    elif extrude[dim]:
                                        x_new.append(a[dim])
                                    else:
                                        x_new.append(a[dim] if vec[j] else b[dim])
                                        j += 1
                                return abs(cs.distance(point, x_new, weights) - epsilon)
                            
                            bounds = []
                            for dim in free_dims:
                                bounds.append((min(a[dim], b[dim]), max(a[dim], b[dim])))
                            first_guess = map(lambda (x, y): (x + y)/2.0, bounds)
                            to_minimize = lambda x: max(epsilon_difference(x, a, self._weights, epsilon_1)**2, epsilon_difference(x, b, other._weights, epsilon_2)**2)
                            
                            opt = scipy.optimize.minimize(to_minimize, first_guess) #tol = 0.000001
                            if opt.success:
                                dist1 = epsilon_difference(opt.x, a, self._weights, epsilon_1)
                                dist2 = epsilon_difference(opt.x, b, other._weights, epsilon_2)
                                between = True
                                k = 0
                                for dim in free_dims:
                                    if not (min(a[dim], b[dim]) <= opt.x[k] <= max(a[dim], b[dim])):
                                        between = False
                                        break
                                    k += 1
                                # must be between a and b on all free dimensions AND must be a sufficiently good solution
                                if dist1 < 0.00001 and dist2 < 0.00001 and between:
                                    point = []
                                    i = 0
                                    j = 0
                                    # puzzle together our large x vector based on the fixed and the free dimensions
                                    for dim in range(cs._n_dim):
                                        if dim in free_dims:
                                            point.append(opt.x[i])
                                            i += 1
                                        elif extrude[dim]:
                                            point.append(a[dim])
                                        else:
                                            point.append(a[dim] if vec[j] else b[dim])
                                            j += 1
                                    
                                    points.append(point)
                                                        
                    if len(points) > 0:
                        # if we found a solution for num_free_dims: stop looking at higher values for num_free_dims
                        p_min = []
                        p_max = []
                        for i in range(cs._n_dim):
                            p_min.append(max(min(a[i],b[i]), reduce(min, map(lambda x: x[i], points))))
                            p_max.append(min(max(a[i],b[i]), reduce(max, map(lambda x: x[i], points))))
                        break
                
                if p_min == None or p_max == None:  
                    # this should never happen - if the weights are dependent, there MUST be a solution
                    raise Exception("Could not find solution for dependent weights")
                
            else:
                # weights are not linearly dependent: use single-point cuboid
                p_min = list(x_star)
                p_max = list(x_star)
                pass
        
        # round everything, because we only found approximate solutions anyways
        mu = cs.round(mu)
        p_min = map(cs.round, p_min)
        p_max = map(cs.round, p_max)
                                                   
        # extrude in remaining dimensions
        for i in range(len(extrude)):
            if extrude[i]:
                p_max[i] = a_range[i][1]

        # finally, construct a cuboid and return it along with mu
        cuboid = cub.Cuboid(p_min, p_max, new_domains)
        
        return mu, cuboid

    def intersect_with(self, other):
        """Computes the intersection of two concepts."""

        if not isinstance(other, Concept):
            raise Exception("Not a valid concept")

        # intersect all cuboids pair-wise in order to get cuboid candidates
        candidates = []
        for c1 in self._core._cuboids:
            for c2 in other._core._cuboids:
                candidates.append(self._intersect_fuzzy_cuboids(c1, c2, other))
        
        mu = reduce(max, map(lambda x: x[0], candidates))
        cuboids = map(lambda x: x[1], filter(lambda y: cs.equal(y[0],mu), candidates))        
        
        # create a repaired core
        core = cor.from_cuboids(cuboids, cuboids[0]._domains)
        
        # calculate new c and new weights
        c = min(self._c, other._c)
        weights = self._weights.merge_with(other._weights, 0.5, 0.5)
        
        return Concept(core, mu, c, weights)

    def unify_with(self, other):
        """Computes the union of two concepts."""

        if not isinstance(other, Concept):
            raise Exception("Not a valid concept")
        
        core = self._core.unify_with(other._core) 
        mu = max(self._mu, other._mu)
        c = min(self._c, other._c)
        weights = self._weights.merge_with(other._weights, 0.5, 0.5)
        
        return Concept(core, mu, c, weights)
        
    def project_onto(self, domains):
        """Computes the projection of this concept onto a subset of domains."""
        
        # no explicit check for domains - Core will take care of this
        new_core = self._core.project_onto(domains)
        new_weights = self._weights.project_onto(domains)
        
        return Concept(new_core, self._mu, self._c, new_weights)

    def cut_at(self, dimension, value):
        """Computes the result of cutting this concept into two parts (at the given value on the given dimension).
        
        Returns the lower part and the upper part as a tuple (lower, upper)."""
        
        lower_core, upper_core = self._core.cut_at(dimension, value)
        lower_concept = None if lower_core == None else Concept(lower_core, self._mu, self._c, self._weights)
        upper_concept = None if upper_core == None else Concept(upper_core, self._mu, self._c, self._weights)
        
        return lower_concept, upper_concept

    def _reduce_domains(self, domains, dimensions):
        """Reduces the domain structure such that only the given dimensions are still contained."""
        new_domains = {}

        for (dom, dims) in domains.items():
            filtered_dims = [dim for dim in set(dims) & set(dimensions)]
            if len(filtered_dims) > 0:
                new_domains[dom] = filtered_dims
        
        return new_domains

    def _hypervolume_couboid(self, cuboid):
        """Computes the hypervolume of a single fuzzified cuboid."""

        all_dims = [dim for domain in self._core._domains.values() for dim in domain]
        n = len(all_dims)

        # calculating the factor in front of the sum
        weight_product = 1.0
        for (dom, dom_weight) in self._weights._domain_weights.items():
            for (dim, dim_weight) in self._weights._dimension_weights[dom].items():
                weight_product *= dom_weight * sqrt(dim_weight)
        factor = self._mu / (self._c**n * weight_product)

        # outer sum
        outer_sum = 0.0        
        for i in range(0, n+1):
            # inner sum
            inner_sum = 0.0
            subsets = list(itertools.combinations(all_dims, i))
            for subset in subsets:
                # first product
                first_product = 1.0
                for dim in set(all_dims) - set(subset):
                    dom = filter(lambda (x,y): dim in y, self._core._domains.items())[0][0]
                    w_dom = self._weights._domain_weights[dom]
                    w_dim = self._weights._dimension_weights[dom][dim]
                    b = cuboid._p_max[dim] - cuboid._p_min[dim]
                    first_product *= w_dom * sqrt(w_dim) * b * self._c
                
                # second product
                second_product = 1.0
                reduced_domain_structure = self._reduce_domains(self._core._domains, subset)
                for (dom, dims) in reduced_domain_structure.items():
                    n_domain = len(dims)
                    second_product *= factorial(n_domain) * (pi ** (n_domain/2.0))/(gamma((n_domain/2.0) + 1))
                
                inner_sum += first_product * second_product
            
            outer_sum += inner_sum
        return factor * outer_sum

    def size(self):
        """Computes the hypervolume of this concept."""
        
        hypervolume = 0.0
        num_cuboids = len(self._core._cuboids)
        
        # use the inclusion-exclusion formula over all the cuboids
        for l in range(1, num_cuboids + 1):
            inner_sum = 0.0

            subsets = list(itertools.combinations(self._core._cuboids, l))           
            for subset in subsets:
                intersection = subset[0]
                for cuboid in subset:
                    intersection = intersection.intersect_with(cuboid)
                inner_sum += self._hypervolume_couboid(intersection)
                
            hypervolume += inner_sum * (-1.0)**(l+1)
        
        return hypervolume

    def subset_of(self, other):
        """Computes the degree of subsethood between this concept and a given other concept."""

        common_domains = {}
        for dom, dims in self._core._domains.iteritems():
            if dom in other._core._domains and other._core._domains[dom] == dims:
                common_domains[dom] = dims
        projected_self = self.project_onto(common_domains)
        projected_other = other.project_onto(common_domains)
        
        intersection = projected_self.intersect_with(projected_other)
        intersection._c = projected_other._c
        intersection._weights = projected_other._weights
        projected_self._c = projected_other._c
        projected_self._weights = projected_other._weights
        subsethood = intersection.size() / projected_self.size()
        return subsethood

    def implies(self, other):
        """Computes the degree of implication between this concept and a given other concept."""
        
        return self.subset_of(other)
    
    def similarity_to(self, other, method="naive"):
        """Computes the similarity of this concept to the given other concept.
        
        The following methods are avaliable:
            'naive':                  similarity of cores' midpoints (used as default)
            'Jaccard':                Jaccard similarity index (size of intersection over size of union)
            'Jaccard_mod':            modified Jaccard similarity index (denominator: self.size() + other.size() - intersection.size())
            'subset':                 use value returned by subset_of()
            'min_core':               similarity based on minimum distance of cores
            'max_core':               similarity based on maximum distance of cores
            'min_membership_core':    minimal membership of any point in self._core to other
            'max_membership_core':    maximal membership of any point in self._core to other
            'Hausdorff_core':         similarity based on Hausdorff distance of cores
            'min_center':             similarity based on minimum distance of cores' central region
            'max_center':             similarity based on maximum distance of cores' central region
            'Hausdorff_center':       similarity based on Hausdorff distance of cores' central region
            'min_membership_center':  minimal membership of any point in self's central region to other
            'max_membership_center':  maximal membership of any point in self's central region to other"""
        
        if method == "naive":
            self_midpoint = self._core.midpoint()
            other_midpoint = other._core.midpoint()
            
            # if the concepts are defined on different domains, choose the midpoints such that their distance is minimized
            for dim in range(cs._n_dim):
                if isnan(self_midpoint[dim]) and isnan(other_midpoint[dim]):
                    self_midpoint[dim] = 0
                    other_midpoint[dim] = 0
                elif isnan(self_midpoint[dim]):
                    self_midpoint[dim] = other_midpoint[dim]
                elif isnan(other_midpoint[dim]):
                    other_midpoint[dim] = self_midpoint[dim]
                    
            sim = exp(-other._c * cs.distance(self_midpoint, other_midpoint, other._weights))
            return sim
        
        elif method == "Jaccard":
            intersection = self.intersect_with(other)
            union = self.unify_with(other)

            intersection._c = other._c
            union._c = other._c
            intersection._weights = other._weights  
            union._weights = other._weights
            
            sim = intersection.size() / union.size()
            return sim
        
        elif method == "Jaccard_mod":
            intersection = self.intersect_with(other)
            self_copy = Concept(self._core, self._mu, other._c, other._weights)

            intersection._c = other._c
            intersection._weights = other._weights  
            
            sim = intersection.size() / (self_copy.size() + other.size() - intersection.size())
            return sim
        
        elif method == "subset":
            return self.subset_of(other)
            
        elif method == "min_core":
            min_dist = float("inf")
            for c1 in self._core._cuboids:
                for c2 in other._core._cuboids:
                    a_range, b_range = c1.get_closest_points(c2)
                    a = map(lambda x: x[0], a_range)
                    b = map(lambda x: x[0], b_range)
                    dist = cs.distance(a, b, other._weights)
                    min_dist = min(min_dist, dist)
            sim = exp(-other._c * min_dist)
            return sim
        
        elif method == "max_core":
            max_dist = 0
            for c1 in self._core._cuboids:
                for c2 in other._core._cuboids:
                    a, b = c1.get_most_distant_points(c2)
                    dist = cs.distance(a, b, other._weights)
                    max_dist = max(max_dist, dist)
            sim = exp(-other._c * max_dist)
            return sim
        
        elif method == "Hausdorff_core":
            self_candidates = []
            other_candidates = []
            for c1 in self._core._cuboids:
                for c2 in other._core._cuboids:
                    a, b = c1.get_most_distant_points(c2)
                    self_candidates.append(a)
                    other_candidates.append(b)
            
            max_dist = 0
            for self_candidate in self_candidates:
                min_dist = float("inf")
                for c2 in other._core._cuboids:
                    p = c2.find_closest_point(self_candidate)
                    min_dist = min(min_dist, cs.distance(self_candidate, p, other._weights))
                max_dist = max(max_dist, min_dist)
            for other_candidate in other_candidates:
                min_dist = float("inf")
                for c1 in self._core._cuboids:
                    p = c1.find_closest_point(other_candidate)
                    min_dist = min(min_dist, cs.distance(other_candidate, p, other._weights))
                max_dist = max(max_dist, min_dist)
            
            sim = exp(-other._c * max_dist)
            return sim
        
        elif method == "min_membership_core":
            candidates = []
            for c1 in self._core._cuboids:
                for c2 in other._core._cuboids:
                    a, b = c1.get_most_distant_points(c2)
                    candidates.append(a)

            min_membership = 1.0            
            for candidate in candidates:
                min_membership = min(min_membership, other.membership_of(candidate))
            
            return min_membership
        
        elif method == "max_membership_core":
            candidates = []
            for c1 in self._core._cuboids:
                for c2 in other._core._cuboids:
                    a, b = c1.get_closest_points(c2)
                    candidates.append(map(lambda x: x[0], a))

            max_membership = 0.0            
            for candidate in candidates:
                max_membership = max(max_membership, other.membership_of(candidate))
            
            return max_membership
        
        elif method == "min_center":
            p1 = self._core.get_center()
            p2 = other._core.get_center()
            a_range, b_range = p1.get_closest_points(p2)
            a = map(lambda x: x[0], a_range)
            b = map(lambda x: x[0], b_range)
            sim = exp(-other._c * cs.distance(a, b, other._weights))
            return sim
        
        elif method == "max_center":
            p1 = self._core.get_center()
            p2 = other._core.get_center()
            a, b = p1.get_most_distant_points(p2)
            sim = exp(-other._c * cs.distance(a, b, other._weights))
            return sim
        
        elif method == "Hausdorff_center":
            p1 = self._core.get_center()
            p2 = other._core.get_center()
            a_distant, b_distant = p1.get_most_distant_points(p2)
            a_close, b_close = p1.get_closest_points(p2)
            
            a = []
            b = []                   
            # find closest point a to b_distant and b to a_distant
            for i in range(cs._n_dim):
                if a_close[i][0] <= b_distant[i] <= a_close[i][1]:
                    a.append(b_distant[i])
                elif b_distant[i] < a_close[i][0]:
                    a.append(a_close[i][0])
                else:
                    a.append(a_close[i][1])
                if b_close[i][0] <= a_distant[i] <= b_close[i][1]:
                    b.append(a_distant[i])
                elif a_distant[i] < b_close[i][0]:
                    b.append(b_close[i][0])
                else:
                    b.append(b_close[i][1])
            
            first_dist = cs.distance(a_distant, b, other._weights)                  
            second_dist = cs.distance(b_distant, a, other._weights)
            sim = exp(-other._c * max(first_dist, second_dist))
            return sim

        elif method == "min_membership_center":
            center = self._core.get_center()
            candidates = []
            for c2 in other._core._cuboids:
                a, b = center.get_most_distant_points(c2)
                candidates.append(a)
            
            min_membership = 1.0
            for candidate in candidates:
                min_membership = min(min_membership, other.membership_of(candidate))
            return min_membership
        
        elif method == "max_membership_center":
            center = self._core.get_center()
            candidates = []
            for c2 in other._core._cuboids:
                a, b = center.get_closest_points(c2)
                candidates.append(map(lambda x: x[0], a))
            
            max_membership = 0.0
            for candidate in candidates:
                max_membership = max(max_membership, other.membership_of(candidate))
            return max_membership
        
        else:
            raise Exception("Unknown method")

    def between(self, first, second, method="naive", n_samples=5000):
        """Computes the degree to which this concept is between the other two given concepts.
        
        The following methods are avaliable:
            'naive':                  crisp betweenness of cores' midpoints (used as default)
            'naive_soft':             soft betweenness of cores' midpoints
            'subset':                 self.subset_of(first.unify_with(second))
            'core':                   core of self is between (in crisp sense) cores of first and second
            'core_soft':              core of self is between (in soft sense) cores of first and second
            'Derrac_Schockaert':      approximation of Btw_3^R proposed by Derrac & Schockaert in 'Enriching Taxonomies of Place Types Using Flickr'
                                      'n_samples' can be used to adjust the number of samples used for computing this approximation."""

        if method == "naive":        
            self_point = self._core.midpoint()
            first_point = first._core.midpoint()
            second_point = second._core.midpoint()
            return cs.between(first_point, self_point, second_point, self._weights, method="crisp")
        
        elif method == "naive_soft":
            self_point = self._core.midpoint()
            first_point = first._core.midpoint()
            second_point = second._core.midpoint()
            return cs.between(first_point, self_point, second_point, self._weights, method="soft")

        elif method == "subset":
            return self.subset_of(first.unify_with(second))

        elif method == "core":
            # create all corner points of all cuboids of this concept
            corner_points = []
            for cuboid in self._core._cuboids:
                binary_vecs = itertools.product([False, True], repeat = cs._n_dim)
                for vec in binary_vecs:
                    point = []
                    for i in range(cs._n_dim):
                        point.append(cuboid._p_max[i] if vec[i] else cuboid._p_min[i])
                    corner_points.append(point)
            
            betweenness = _check_crisp_betweenness(corner_points, first, second)
            remaining_corners = list(itertools.compress(corner_points, map(lambda x: not x, betweenness)))
            if len(remaining_corners) > 0:
                return 0.0
            return 1.0
            
        elif method == "core_soft":
            # create all corner points of all cuboids of this concept
            corner_points = []
            corner_bounds = []
            for cuboid in self._core._cuboids:
                binary_vecs = itertools.product([False, True], repeat = cs._n_dim)
                cuboid_bounds = zip(cuboid._p_min, cuboid._p_max)
                for vec in binary_vecs:
                    point = []
                    for i in range(cs._n_dim):
                        point.append(cuboid._p_max[i] if vec[i] else cuboid._p_min[i])
                    corner_points.append(point)
                    corner_bounds.append(cuboid_bounds)

            # remove all corners that are already between in a crisp sense
            crisp_betweenness = _check_crisp_betweenness(corner_points, first, second)
            to_keep = map(lambda x: not x, crisp_betweenness)
            remaining_corners = list(itertools.compress(corner_points, to_keep))
            remaining_bounds = list(itertools.compress(corner_bounds, to_keep))

            # completely between in crisp sense: can safely return 1.0
            if len(remaining_corners) == 0:
                return 1.0

            # store the maximum betweenness value we have found starting from the ith corner point
            max_betweenness = [0.0]*len(remaining_corners)            
            
            for c1 in first._core._cuboids:
                for c2 in second._core._cuboids:
                    
                    if not c1._compatible(c2):
                        raise Exception("Incompatible cuboids")
                        
                    x_bounds = zip(c1._p_min, c1._p_max) + zip(c2._p_min, c2._p_max)
                    
                    # maximizing over x in c1 and z in c2; for convenience, do this at the same time
                    def inner_optimization(y):
                        x_start = list(map(lambda x: 0.5*x[0] + 0.5*x[1], x_bounds))
                        to_minimize_x = lambda x, y: -1*cs.between(x[:cs._n_dim], y, x[-cs._n_dim:], self._weights, method='soft')
                        opt = scipy.optimize.minimize(to_minimize_x, x_start, args=(y,), bounds=x_bounds, options={'gtol':cs._epsilon})
                        if not opt.success:
                            raise Exception("optimization failed")
                        return opt
                
                    # minimizing over y in self
                    for i in range(len(remaining_corners)):
                        corner = remaining_corners[i]
                        bounds = remaining_bounds[i]
                        to_minimize_y = lambda y: -1 * inner_optimization(y).fun
                        opt = scipy.optimize.minimize(to_minimize_y, corner, bounds=bounds, options={'gtol':cs._epsilon})
                        if not opt.success:
                            raise Exception("optimization failed")
                        max_betweenness[i] = max(max_betweenness[i], opt.fun)
            
            return min(max_betweenness)

        elif method == "Derrac_Schockaert":
            # 1 / (size of self._core) * sum_{y in self._core}: max_{x in first._core, z in second._core} cs.between(x,y,z, method='soft')
            # cannot compute this directly (infinitely many points in our cuboids), integral would be complicated
            # --> approximate it by sampling points from self._core (using grids over cuboids)
            
            cuboid_widths = []
            for cuboid in self._core._cuboids:
                cuboid_widths.append(list(map(lambda x, y: 1.0 * (x - y), cuboid._p_max, cuboid._p_min)))
            
            cuboid_sizes = []
            for vec in cuboid_widths:
                cuboid_sizes.append(reduce(lambda x, y: x * y if y != 0 else x, vec))   # if we have 0 width, don't make overall size 0
            overall_size = sum(cuboid_sizes)
            
            # larger cuboids get more samples than smaller ones
            samples_per_cuboid = list(map(lambda x: round(1.0 * x * n_samples / overall_size), cuboid_sizes))
            samples = []

            # create a grid for each cuboid and its points to the samples
            for i in range(len(self._core._cuboids)):
                samples_per_dim = []
                widths = cuboid_widths[i]
                p_min = self._core._cuboids[i]._p_min
                n_samples = samples_per_cuboid[i]
                n_dim = sum(map(lambda x: 0.0 if isnan(x) else 1.0, widths))

                n_0 = round(((1.0 * n_samples * (widths[0]) ** n_dim)/ cuboid_sizes[i]) ** (1.0/n_dim))
                samples_per_dim.append(n_0)

                for j in range(1, int(n_dim)):
                    samples_per_dim.append(max(1.0, round(n_0 * (widths[j]/widths[0])))) # max takes care of dimensions with zero width
                
                step_sizes = list(map(lambda x, y: x / max(y - 1.0, 1.0), widths, samples_per_dim)) # max takes care of dimensions with zero width

                coordinates = []
                for j in range(int(n_dim)):
                    local_coords = []
                    for k in range(int(samples_per_dim[j])):
                        local_coords.append(p_min[j] + k * step_sizes[j])
                    coordinates.append(local_coords)
                
                samples = samples + list(itertools.product(*coordinates))

            if len(samples) == 0:
                print "ERROR"
            crisp_between = _check_crisp_betweenness(samples, first, second)
            betweenness = list(map(lambda x: 1.0 if x else 0.0, crisp_between))
            for c1 in first._core._cuboids:
                for c2 in second._core._cuboids:
                    
                    if not c1._compatible(c2):
                        raise Exception("Incompatible cuboids")
                        
                    x_bounds = zip(c1._p_min, c1._p_max) + zip(c2._p_min, c2._p_max)
                    x_start = list(map(lambda x: 0.5*x[0] + 0.5*x[1], x_bounds))
                    for i in range(len(samples)):
                        if crisp_between[i]:
                            continue
                        point = samples[i]
                        to_minimize = lambda x: -1*cs.between(x[:cs._n_dim], point, x[-cs._n_dim:], self._weights, method='soft')
                        opt = scipy.optimize.minimize(to_minimize, x_start, bounds=x_bounds)
                        if not opt.success:
                            print opt
                            raise Exception("Optimization failed")
                        if betweenness[i] < -1 * opt.fun:
                            betweenness[i] = -1 * opt.fun
                            
            return sum(betweenness) / float(len(betweenness))

        else:
            raise Exception("Unknown method")


def _check_crisp_betweenness(points, first, second):
    """Returns a list of boolean flags indicating which of the given points are strictly between the first and the second concept."""
    
    # store whether the ith point has already be shown to be between the two other cores
    betweenness = [False]*len(points)

    for c1 in first._core._cuboids:
        for c2 in second._core._cuboids:
            
            if not c1._compatible(c2):
                raise Exception("Incompatible cuboids")
            p_min = map(min, c1._p_min, c2._p_min)
            p_max = map(max, c1._p_max, c2._p_max)
            dom_union = dict(c1._domains)
            dom_union.update(c2._domains)         
            bounding_box = cub.Cuboid(p_min, p_max, dom_union)

            local_betweenness = [True]*len(points)                    
            # check if each point is contained in the bounding box
            for i in range(len(points)):
                local_betweenness[i] = bounding_box.contains(points[i])
            
            if reduce(lambda x,y: x or y, local_betweenness) == False:  # no need to check inequalities
                continue
            
            # check additional contraints for each domain
            for domain in dom_union.values():
                if len(domain) < 2: # we can safely ignore one-dimensional domains
                    continue
                
                for i in range(len(domain)):
                    for j in range(i+1, len(domain)):
                        # look at all pairs of dimensions within this domain                                
                        d1 = domain[i]
                        d2 = domain[j]

                        # create list of inequalities
                        inequalities = []
                        def makeInequality(p1, p2, below):
                            sign = -1 if below else 1
                            a = (p2[1] - p1[1]) if p2[0] > p1[0] else (p1[1] - p2[1])
                            b = -abs(p1[0] - p2[0])
                            c = -1 * (a * p1[0] + b * p1[1])
                            return (lambda x: (sign * (a * x[0] + b * x[1] + c) <= 0))

                        # different cases
                        if c2._p_max[d1] > c1._p_max[d1] and c2._p_min[d2] > c1._p_min[d2]:
                            inequalities.append(makeInequality([c1._p_max[d1], c1._p_min[d2]], [c2._p_max[d1], c2._p_min[d2]], False))
                        if c2._p_max[d1] > c1._p_max[d1] and c1._p_max[d2] > c2._p_max[d2]:
                            inequalities.append(makeInequality(c1._p_max, c2._p_max, True))
                        if c2._p_min[d1] > c1._p_min[d1] and c2._p_max[d2] > c1._p_max[d2]:
                            inequalities.append(makeInequality([c1._p_min[d1], c1._p_max[d2]], [c2._p_min[d1], c2._p_max[d2]], True))
                        if c2._p_min[d1] > c1._p_min[d1] and c2._p_min[d2] < c1._p_min[d2]:
                            inequalities.append(makeInequality(c1._p_min, c2._p_min, False))
                        
                        if c1._p_max[d1] > c2._p_max[d1] and c1._p_min[d2] > c2._p_min[d2]:
                            inequalities.append(makeInequality([c1._p_max[d1], c1._p_min[d2]], [c2._p_max[d1], c2._p_min[d2]], False))
                        if c1._p_max[d1] > c2._p_max[d1] and c2._p_max[d2] > c1._p_max[d2]:
                            inequalities.append(makeInequality(c1._p_max, c2._p_max, True))
                        if c1._p_min[d1] > c2._p_min[d1] and c1._p_max[d2] > c2._p_max[d2]:
                            inequalities.append(makeInequality([c1._p_min[d1], c1._p_max[d2]], [c2._p_min[d1], c2._p_max[d2]], True))
                        if c1._p_min[d1] > c2._p_min[d1] and c1._p_min[d2] < c2._p_min[d2]:
                            inequalities.append(makeInequality(c1._p_min, c2._p_min, False))
                        
                        
                        for k in range(len(points)):
                            for ineq in inequalities:
                                local_betweenness[k] = local_betweenness[k] and ineq([points[k][d1], points[k][d2]])

                        if not reduce(lambda x, y: x or y, local_betweenness):
                            break
                    if not reduce(lambda x, y: x or y, local_betweenness):
                            break
                if not reduce(lambda x, y: x or y, local_betweenness):
                            break
                        
            betweenness = map(lambda x, y: x or y, betweenness, local_betweenness)
            if reduce(lambda x, y: x and y, betweenness):
                return betweenness
    
    return betweenness
