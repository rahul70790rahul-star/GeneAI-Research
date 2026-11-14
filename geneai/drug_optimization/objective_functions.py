"""Objective functions for multi-objective drug optimization."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class OptimizationObjective:
    """Single optimization objective."""
    name: str
    function: Callable[[dict[str, float]], float]  # properties -> score
    target: float | None = None  # Target value (if applicable)
    weight: float = 1.0
    minimize: bool = True  # True = minimize, False = maximize
    constraint: tuple[float, float] | None = None  # (min, max) hard constraint
    penalty_weight: float = 100.0  # Penalty for constraint violation


@dataclass
class ObjectiveResult:
    """Result of objective evaluation."""
    name: str
    value: float
    score: float  # Normalized/weighted score
    constraint_satisfied: bool = True
    penalty: float = 0.0


class ObjectiveFunctionRegistry:
    """Registry of predefined objective functions."""
    
    # Property names that can be used in objectives
    PROPERTY_NAMES = [
        "mw", "logp", "tpsa", "hbd", "hba", "rotatable_bonds",
        "qed", "sa_score", "fsp3", "aromatic_rings", "formal_charge",
        "caco2", "hia", "pgp_substrate", "pgp_inhibitor", "bioavailability",
        "bbb", "cns_mpo", "vdss", "plasma_protein_binding",
        "cyp1a2_inhibitor", "cyp2c9_inhibitor", "cyp2c19_inhibitor",
        "cyp2d6_inhibitor", "cyp3a4_inhibitor",
        "cyp1a2_substrate", "cyp2c9_substrate", "cyp2c19_substrate",
        "cyp2d6_substrate", "cyp3a4_substrate",
        "clearance", "half_life", "renal_clearance",
        "ames", "hepatotoxicity", "herg", "skin_sensitization",
        "ld50_category", "carcinogenicity",
        "docking_score", "binding_affinity",
    ]
    
    def __init__(self):
        self.objectives: dict[str, OptimizationObjective] = {}
        self._register_defaults()
    
    def _register_defaults(self):
        """Register default drug discovery objectives."""
        
        # Potency objectives (from docking or predicted)
        self.register(OptimizationObjective(
            name="potency",
            function=lambda props: -props.get("docking_score", 0),  # Lower docking score = better
            target=-10.0,  # Target -10 kcal/mol
            weight=0.30,
            minimize=True,
            constraint=(-15.0, -5.0),
        ))
        
        self.register(OptimizationObjective(
            name="binding_affinity",
            function=lambda props: -props.get("binding_affinity", 0),  # Higher affinity = better
            target=9.0,  # Target pIC50 > 9
            weight=0.25,
            minimize=False,  # Maximize affinity
            constraint=(7.0, 12.0),
        ))
        
        # ADMET objectives
        self.register(OptimizationObjective(
            name="bbb_permeability",
            function=lambda props: props.get("bbb", -2),  # logBB
            target=0.3,  # Target logBB > 0.3
            weight=0.15,
            minimize=False,
            constraint=(-1.0, 2.0),
        ))
        
        self.register(OptimizationObjective(
            name="cns_mpo",
            function=lambda props: props.get("cns_mpo", 0),
            target=5.0,  # Target CNS MPO > 5
            weight=0.10,
            minimize=False,
            constraint=(3.0, 6.0),
        ))
        
        # Safety objectives (minimize)
        self.register(OptimizationObjective(
            name="cyp3a4_inhibition",
            function=lambda props: props.get("cyp3a4_inhibitor", 0),
            target=0.1,  # Target < 0.1 probability
            weight=0.20,
            minimize=True,
            constraint=(0.0, 0.5),
        ))
        
        self.register(OptimizationObjective(
            name="cyp2d6_inhibition",
            function=lambda props: props.get("cyp2d6_inhibitor", 0),
            target=0.1,
            weight=0.15,
            minimize=True,
            constraint=(0.0, 0.5),
        ))
        
        self.register(OptimizationObjective(
            name="herg_toxicity",
            function=lambda props: props.get("herg", 0),
            target=0.1,  # Target < 0.1 probability
            weight=0.20,
            minimize=True,
            constraint=(0.0, 0.3),
        ))
        
        self.register(OptimizationObjective(
            name="ames_mutagenicity",
            function=lambda props: props.get("ames", 0),
            target=0.05,
            weight=0.15,
            minimize=True,
            constraint=(0.0, 0.3),
        ))
        
        self.register(OptimizationObjective(
            name="hepatotoxicity",
            function=lambda props: props.get("hepatotoxicity", 0),
            target=0.1,
            weight=0.10,
            minimize=True,
            constraint=(0.0, 0.3),
        ))
        
        # Physicochemical objectives
        self.register(OptimizationObjective(
            name="molecular_weight",
            function=lambda props: props.get("mw", 500),
            target=400,  # Target ~400 Da
            weight=0.05,
            minimize=False,  # Close to target
            constraint=(250, 500),
        ))
        
        self.register(OptimizationObjective(
            name="logp",
            function=lambda props: props.get("logp", 3),
            target=3.0,  # Target LogP ~3
            weight=0.05,
            minimize=False,
            constraint=(1.0, 5.0),
        ))
        
        self.register(OptimizationObjective(
            name="tpsa",
            function=lambda props: props.get("tpsa", 100),
            target=80,  # Target TPSA ~80
            weight=0.05,
            minimize=False,
            constraint=(40, 120),
        ))
        
        self.register(OptimizationObjective(
            name="solubility",
            function=lambda props: -props.get("logp", 3) - 0.01 * props.get("mw", 400),  # Approx logS
            target=-4,  # Target logS > -4
            weight=0.05,
            minimize=False,
            constraint=(-6, -1),
        ))
        
        self.register(OptimizationObjective(
            name="sa_score",
            function=lambda props: props.get("sa_score", 3),
            target=2.5,  # Target SA Score < 2.5
            weight=0.10,
            minimize=True,
            constraint=(1.0, 4.0),
        ))
        
        self.register(OptimizationObjective(
            name="fsp3",
            function=lambda props: props.get("fsp3", 0.3),
            target=0.5,  # Target Fsp3 > 0.5
            weight=0.05,
            minimize=False,
            constraint=(0.2, 1.0),
        ))
        
        # Lipinski compliance (soft constraint)
        self.register(OptimizationObjective(
            name="lipinski_compliance",
            function=lambda props: sum([
                1 if props.get("mw", 0) > 500 else 0,
                1 if props.get("logp", 0) > 5 else 0,
                1 if props.get("hbd", 0) > 5 else 0,
                1 if props.get("hba", 0) > 10 else 0,
            ]),
            target=0,
            weight=0.10,
            minimize=True,
            constraint=(0, 1),
        ))
    
    def register(self, objective: OptimizationObjective):
        """Register an objective."""
        self.objectives[objective.name] = objective
    
    def get(self, name: str) -> OptimizationObjective | None:
        """Get objective by name."""
        return self.objectives.get(name)
    
    def get_all(self) -> list[OptimizationObjective]:
        """Get all registered objectives."""
        return list(self.objectives.values())
    
    def create_objective_set(self, names: list[str]) -> list[OptimizationObjective]:
        """Create objective set from names."""
        return [self.objectives[n] for n in names if n in self.objectives]


class MultiObjectiveEvaluator:
    """Evaluate molecules against multiple objectives."""
    
    def __init__(self, objectives: list[OptimizationObjective] | None = None):
        if objectives is None:
            registry = ObjectiveFunctionRegistry()
            objectives = registry.get_all()
        self.objectives = objectives
        self.logger = logging.getLogger(__name__)
    
    def evaluate(self, properties: dict[str, float]) -> dict[str, ObjectiveResult]:
        """Evaluate all objectives for a molecule."""
        results = {}
        
        for obj in self.objectives:
            try:
                value = obj.function(properties)
                
                # Check constraint
                constraint_satisfied = True
                penalty = 0.0
                
                if obj.constraint:
                    min_val, max_val = obj.constraint
                    if value < min_val or value > max_val:
                        constraint_satisfied = False
                        # Quadratic penalty
                        if value < min_val:
                            penalty = obj.penalty_weight * (min_val - value) ** 2
                        else:
                            penalty = obj.penalty_weight * (value - max_val) ** 2
                
                # Normalize score based on target
                if obj.target is not None:
                    if obj.minimize:
                        # Lower is better
                        if obj.constraint:
                            min_val, max_val = obj.constraint
                            normalized = (max_val - value) / (max_val - min_val) if max_val != min_val else 1.0
                        else:
                            normalized = 1.0 / (1.0 + abs(value - obj.target))
                    else:
                        # Higher is better
                        if obj.constraint:
                            min_val, max_val = obj.constraint
                            normalized = (value - min_val) / (max_val - min_val) if max_val != min_val else 1.0
                        else:
                            normalized = value / (value + abs(obj.target)) if obj.target > 0 else 0.5
                else:
                    normalized = 1.0
                
                # Apply weight
                score = normalized * obj.weight - penalty
                
                results[obj.name] = ObjectiveResult(
                    name=obj.name,
                    value=value,
                    score=score,
                    constraint_satisfied=constraint_satisfied,
                    penalty=penalty,
                )
                
            except Exception as e:
                self.logger.warning("Objective %s evaluation failed: %s", obj.name, e)
                results[obj.name] = ObjectiveResult(
                    name=obj.name,
                    value=0.0,
                    score=-1000.0,
                    constraint_satisfied=False,
                    penalty=1000.0,
                )
        
        return results
    
    def total_score(self, properties: dict[str, float]) -> float:
        """Calculate total weighted score."""
        results = self.evaluate(properties)
        return sum(r.score for r in results.values())
    
    def pareto_dominates(self, props1: dict[str, float], props2: dict[str, float]) -> bool:
        """Check if props1 Pareto dominates props2."""
        results1 = self.evaluate(props1)
        results2 = self.evaluate(props2)
        
        better_in_any = False
        for name in results1:
            r1 = results1[name]
            r2 = results2[name]
            obj = self.get_objective(name)
            
            if obj and obj.minimize:
                if r1.value > r2.value:
                    return False
                if r1.value < r2.value:
                    better_in_any = True
            else:
                if r1.value < r2.value:
                    return False
                if r1.value > r2.value:
                    better_in_any = True
        
        return better_in_any
    
    def get_objective(self, name: str) -> OptimizationObjective | None:
        for obj in self.objectives:
            if obj.name == name:
                return obj
        return None


def create_default_evaluator() -> MultiObjectiveEvaluator:
    """Create evaluator with default drug discovery objectives."""
    registry = ObjectiveFunctionRegistry()
    
    # Select key objectives for drug discovery
    selected = [
        "potency", "binding_affinity",
        "bbb_permeability", "cns_mpo",
        "cyp3a4_inhibition", "cyp2d6_inhibition",
        "herg_toxicity", "ames_mutagenicity", "hepatotoxicity",
        "molecular_weight", "logp", "tpsa", "solubility",
        "sa_score", "fsp3", "lipinski_compliance",
    ]
    
    objectives = registry.create_objective_set(selected)
    return MultiObjectiveEvaluator(objectives)


def create_cns_optimization_evaluator() -> MultiObjectiveEvaluator:
    """Create evaluator optimized for CNS drugs."""
    registry = ObjectiveFunctionRegistry()
    
    selected = [
        "potency", "binding_affinity",
        "bbb_permeability", "cns_mpo",
        "cyp3a4_inhibition", "cyp2d6_inhibition",
        "herg_toxicity", "ames_mutagenicity",
        "molecular_weight", "logp", "tpsa", "solubility",
        "sa_score", "fsp3", "lipinski_compliance",
    ]
    
    # Increase CNS weights
    objectives = registry.create_objective_set(selected)
    for obj in objectives:
        if obj.name in ["bbb_permeability", "cns_mpo"]:
            obj.weight *= 2.0
        if obj.name in ["cyp3a4_inhibition", "cyp2d6_inhibition", "herg_toxicity"]:
            obj.weight *= 1.5
    
    return MultiObjectiveEvaluator(objectives)


def create_peripheral_optimization_evaluator() -> MultiObjectiveEvaluator:
    """Create evaluator optimized for peripheral drugs (avoid BBB)."""
    registry = ObjectiveFunctionRegistry()
    
    selected = [
        "potency", "binding_affinity",
        "bbb_permeability",  # Want LOW BBB
        "cyp3a4_inhibition", "cyp2d6_inhibition",
        "herg_toxicity", "ames_mutagenicity", "hepatotoxicity",
        "molecular_weight", "logp", "tpsa", "solubility",
        "sa_score", "lipinski_compliance",
    ]
    
    objectives = registry.create_objective_set(selected)
    for obj in objectives:
        if obj.name == "bbb_permeability":
            # Want low BBB permeability
            obj.minimize = True
            obj.target = -1.0
            obj.weight *= 2.0
    
    return MultiObjectiveEvaluator(objectives)