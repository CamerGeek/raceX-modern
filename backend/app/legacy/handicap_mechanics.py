#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Handicap Mechanics Integration for Trotting Races
Handles distance penalties, earning thresholds, catch-up effort calculations
"""

import pandas as pd
import numpy as np
import re
from typing import Optional, Dict, List, Tuple


class HandicapAnalyzer:
    """
    Analyzes handicap conditions in trotting races.
    
    Key concepts:
    - Distance penalty: 25m or 50m starting position disadvantage
    - Earnings threshold: Cap (e.g., "€50,000") to qualify for penalty
    - Catch-up effort: Extra speed required to overcome distance
    - DQ risk amplification: Penalized horses face higher disqualification risk
    - Drafting advantage: Following horses without penalty
    """
    
    # Constants for effort/speed calculations
    TROTTING_SPEED_KMH = 35  # Average trotting speed
    CATCH_UP_MULTIPLIER_25M = 1.08  # 8% extra effort for 25m penalty
    CATCH_UP_MULTIPLIER_50M = 1.16  # 16% extra effort for 50m penalty
    DQ_RISK_AMPLIFIER_25M = 1.15  # 15% higher DQ risk with 25m
    DQ_RISK_AMPLIFIER_50M = 1.35  # 35% higher DQ risk with 50m
    
    @staticmethod
    def detect_handicap_from_distances(dist_column) -> Optional[int]:
        """
        Detect handicap penalty from DIST. column.
        If multiple distances exist, the penalty = max_distance - min_distance.
        Returns: 25, 50, or None
        
        Logic:
        - Only 1 unique distance → no handicap (return None)
        - 2+ unique distances → handicap exists
        - Penalty distance = max(DIST.) - min(DIST.)
        
        Example:
        - [2700, 2700, 2700] → no handicap
        - [2700, 2725, 2700] → handicap 25m
        - [2700, 2750, 2700] → handicap 50m
        """
        if dist_column is None:
            return None
        
        try:
            # Convert to numeric, extract integer distance values
            distances = []
            for val in dist_column:
                if pd.notna(val):
                    # Extract numeric part from strings like "2700m"
                    dist_str = str(val).strip()
                    dist_num = int(''.join(filter(str.isdigit, dist_str)))
                    if dist_num > 0:
                        distances.append(dist_num)
            
            if not distances or len(set(distances)) <= 1:
                return None  # No handicap
            
            # Calculate penalty distance
            min_dist = min(distances)
            max_dist = max(distances)
            penalty = max_dist - min_dist
            
            # Only 25m or 50m are standard handicaps
            if penalty in (25, 50):
                return penalty
            elif penalty < 25:
                return 25  # Round down to 25m
            elif penalty < 50:
                return 50  # Round to 50m
            else:
                return penalty  # Other non-standard penalties
        
        except Exception as e:
            print(f"[DEBUG] Error detecting handicap from distances: {e}")
            return None
    
    @staticmethod
    def extract_handicap_type(race_conditions: str) -> Optional[int]:
        """
        Extract handicap distance penalty from race conditions.
        Returns: 25, 50, or None
        
        Example inputs:
        - "Handicap - 25m for horses over €50,000"
        - "Handicap 50m - Class 2"
        - "Handicap (25 mètres)"
        
        NOTE: Prefer detect_handicap_from_distances() if DIST. column available.
        """
        if not race_conditions or not isinstance(race_conditions, str):
            return None
        
        # Search for handicap distance patterns
        patterns = [
            r'handicap[\s-]*(\d+)\s*(?:m|mètres)',  # "handicap 25m", "handicap-50 mètres"
            r'(\d+)\s*(?:m|mètres)[\s-]*handicap',  # "25m handicap", "50 mètres-handicap"
        ]
        
        for pattern in patterns:
            match = re.search(pattern, race_conditions, re.IGNORECASE)
            if match:
                distance = int(match.group(1))
                if distance in (25, 50):
                    return distance
        
        return None
    
    @staticmethod
    def extract_earnings_threshold(race_conditions: str) -> Optional[float]:
        """
        Extract earnings threshold from race conditions.
        Returns: Earnings threshold in euros, or None
        
        Example inputs:
        - "for horses that have not won €50,000"
        - "Handicap - max earnings: 75,000€"
        - "Horses over €100.000"
        """
        if not race_conditions or not isinstance(race_conditions, str):
            return None
        
        patterns = [
            r'(?:€|euros?|not won|over)\s*(\d+[.,]?\d*)\s*(?:€|k)?',
            r'(\d+[.,]?\d*)\s*€',
            r'earnings?[:\s]*(\d+[.,]?\d*)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, race_conditions, re.IGNORECASE)
            if match:
                value_str = match.group(1).replace(',', '.')
                value = float(value_str) * 1000 if value_str.isdigit() and len(value_str) <= 3 else float(value_str)
                return value
        
        return None
    
    @staticmethod
    def get_handicap_classification(horse_earnings: float, threshold: float) -> Tuple[bool, str]:
        """
        Classify horse as penalized or not based on earnings vs threshold.
        
        Returns: (is_penalized: bool, reason: str)
        
        Examples:
        - (True, "Over threshold") - horse exceeded earnings cap
        - (False, "Below threshold") - horse eligible for starting post advantage
        """
        if threshold is None:
            return False, "No threshold"
        
        is_penalized = horse_earnings > threshold
        reason = "Over threshold" if is_penalized else "Below threshold"
        return is_penalized, reason
    
    @staticmethod
    def calculate_catch_up_effort(handicap_distance: int, 
                                   current_fitness: float,
                                   race_distance: float = 2700) -> float:
        """
        Calculate the extra effort multiplier needed to catch up from handicap.
        
        Args:
            handicap_distance: 25 or 50 meters
            current_fitness: FA/FM value (lower = better fitness)
            race_distance: Total race distance in meters
        
        Returns: Effort multiplier (1.0 = no handicap, >1.0 = extra effort needed)
        
        Formula:
        - Base multiplier: 1.08 for 25m, 1.16 for 50m
        - Fitness adjustment: Better fitness (lower FA) reduces effort needed
        - Adjusted = base_multiplier * (fitness_factor)
        """
        if handicap_distance == 25:
            base_multiplier = HandicapAnalyzer.CATCH_UP_MULTIPLIER_25M
        elif handicap_distance == 50:
            base_multiplier = HandicapAnalyzer.CATCH_UP_MULTIPLIER_50M
        else:
            return 1.0
        
        # Fitness adjustment: FA/FM scales 1-10
        # Better fitness (FA=1) = less adjustment needed
        # Worse fitness (FA=10) = more effort needed
        fitness_factor = 1.0 + (current_fitness - 1) * 0.02  # Each fitness point adds ~2%
        
        # Distance ratio: longer races reduce impact
        distance_factor = 2700 / max(race_distance, 1)
        
        adjusted_multiplier = base_multiplier * fitness_factor * distance_factor
        return round(adjusted_multiplier, 3)
    
    @staticmethod
    def calculate_dq_risk_amplification(handicap_distance: int,
                                         base_dq_risk: float,
                                         fitness: float) -> float:
        """
        Amplify disqualification risk based on handicap penalty and fitness.
        
        Args:
            handicap_distance: 25 or 50 meters
            base_dq_risk: Current DQ risk score (0-100)
            fitness: FA/FM value (1-10)
        
        Returns: Amplified DQ risk score (0-100+)
        
        Rationale:
        - Penalized horses must run faster to catch up
        - Faster running = higher break-into-canter risk
        - Poor fitness amplifies this risk
        """
        if handicap_distance == 25:
            amplifier = HandicapAnalyzer.DQ_RISK_AMPLIFIER_25M
        elif handicap_distance == 50:
            amplifier = HandicapAnalyzer.DQ_RISK_AMPLIFIER_50M
        else:
            return base_dq_risk
        
        # Fitness multiplier: bad fitness (high FA) amplifies further
        fitness_multiplier = 1.0 + (fitness - 1) * 0.05
        
        amplified_risk = base_dq_risk * amplifier * fitness_multiplier
        return round(min(amplified_risk, 100), 2)
    
    @staticmethod
    def calculate_drafting_bonus(is_penalized: bool,
                                  num_non_penalized_ahead: int,
                                  base_performance_score: float) -> float:
        """
        Calculate performance bonus from drafting (following non-penalized horses).
        
        Args:
            is_penalized: Whether this horse is penalized
            num_non_penalized_ahead: Count of non-penalized horses this one can follow
            base_performance_score: Base success coefficient
        
        Returns: Drafting bonus percentage
        
        Strategy:
        - Penalized horses benefit from drafting
        - Each non-penalized horse ahead = +2% performance bonus
        - Max bonus = +10% (5+ horses)
        """
        if not is_penalized or num_non_penalized_ahead == 0:
            return 0.0
        
        # Each non-penalized horse = 2% benefit, max 10%
        bonus = min(num_non_penalized_ahead * 2, 10)
        return bonus
    
    @staticmethod
    def calculate_threshold_edge_advantage(horse_earnings: float,
                                            threshold: float,
                                            penalized_horses_count: int,
                                            total_horses: int) -> float:
        """
        Calculate advantage for horses just under the threshold.
        
        Args:
            horse_earnings: Horse's total earnings
            threshold: Handicap threshold
            penalized_horses_count: Total horses penalized in race
            total_horses: Total horses in race
        
        Returns: Advantage score (-10 to +10)
        
        Rationale:
        - A horse at €49,500 with €50,000 threshold is advantaged
        - It avoids penalty while competing in same class
        - Advantage scales with % of field that's penalized
        """
        if threshold is None:
            return 0.0
        
        # How close to threshold? 0-100 scale
        if horse_earnings >= threshold:
            return 0.0  # Already penalized
        
        distance_to_threshold = threshold - horse_earnings
        threshold_pct = distance_to_threshold / threshold * 100
        
        # Closer to threshold = more advantage
        # Cap at 5% below threshold
        edge_advantage = min(threshold_pct / 5, 1.0) * 5  # Scale 0-5
        
        # Multiply by % of field penalized (higher = more valuable advantage)
        penalty_rate = penalized_horses_count / max(total_horses, 1)
        adjusted_advantage = edge_advantage * (1 + penalty_rate)
        
        return round(adjusted_advantage, 2)


def analyze_handicap_impact(race_df: pd.DataFrame, 
                             race_conditions: Optional[str] = None,
                             race_distance: float = 2700) -> pd.DataFrame:
    """
    Comprehensive handicap analysis for all horses in a race.
    
    Args:
        race_df: Race dataframe with columns like CHEVAL, DERNIÈRES PERF., DIST., etc.
        race_conditions: Race conditions text (optional, for text-based detection fallback)
        race_distance: Average race distance in meters (default 2700)
    
    Returns: DataFrame with handicap analysis columns added
    
    Detection strategy (in order):
    1. Try DIST. column (most reliable) - if multiple distances found, it's a handicap
    2. Fall back to parsing race_conditions text
    3. If neither works, no handicap (all horses get neutral scores)
    
    New columns added:
    - HANDICAP_DISTANCE: 25, 50, or None
    - EARNINGS_THRESHOLD: Earnings cap in euros (if available in data)
    - IS_PENALIZED: Boolean, whether horse has greater DIST. than minimum
    - CATCH_UP_EFFORT: Multiplier for extra effort needed (1.0 = no penalty)
    - AMPLIFIED_DQ_RISK: Disqualification risk with handicap adjustment
    - DRAFTING_BONUS: Performance benefit from following non-penalized horses
    - THRESHOLD_EDGE_ADVANTAGE: Advantage for horses just under threshold
    - HANDICAP_ADJUSTED_SCORE: Overall performance adjustment from handicap
    """
    analyzer = HandicapAnalyzer()
    df = race_df.copy()
    
    # STRATEGY 1: Detect from DIST. column (most reliable)
    handicap_distance = None
    min_dist = None
    
    if 'DIST.' in df.columns:
        handicap_distance = analyzer.detect_handicap_from_distances(df['DIST.'])
        
        # Get minimum distance for classification
        try:
            distances = []
            for val in df['DIST.']:
                if pd.notna(val):
                    dist_str = str(val).strip()
                    dist_num = int(''.join(filter(str.isdigit, dist_str)))
                    if dist_num > 0:
                        distances.append(dist_num)
            if distances:
                min_dist = min(distances)
        except:
            pass
    
    # STRATEGY 2: Fall back to race_conditions text parsing
    if handicap_distance is None:
        handicap_distance = analyzer.extract_handicap_type(race_conditions or "")
    
    # Get earnings threshold (fallback to race_conditions parsing)
    earnings_threshold = analyzer.extract_earnings_threshold(race_conditions or "")
    
    # Initialize result columns
    df['HANDICAP_DISTANCE'] = handicap_distance
    df['EARNINGS_THRESHOLD'] = earnings_threshold
    
    if handicap_distance is None:
        # No handicap race - all horses get neutral scores
        df['IS_PENALIZED'] = False
        df['CATCH_UP_EFFORT'] = 1.0
        df['AMPLIFIED_DQ_RISK'] = df.get('DQ_Risk', 0)
        df['DRAFTING_BONUS'] = 0.0
        df['THRESHOLD_EDGE_ADVANTAGE'] = 0.0
        df['HANDICAP_ADJUSTED_SCORE'] = 1.0
        return df
    
    # HANDICAP RACE: Classify horses based on DIST. column
    handicap_data = []
    
    for idx, row in df.iterrows():
        # Get this horse's distance
        horse_dist = None
        if 'DIST.' in row and pd.notna(row['DIST.']):
            dist_str = str(row['DIST.']).strip()
            horse_dist = int(''.join(filter(str.isdigit, dist_str)))
        
        # Classify as penalized or not
        # Penalized = distance > min_dist (same penalty type for all)
        if min_dist and horse_dist and horse_dist > min_dist:
            is_penalized = True
        else:
            is_penalized = False
        
        # Get fitness for catch-up calculation
        fitness = row.get('FA', row.get('FM', 5))  # Default to 5 if not available
        dq_risk = row.get('DQ_Risk', 50)  # Default to 50 if not available
        s_coeff = row.get('S_COEFF', 0.5)  # Success coefficient
        
        # Calculate impacts
        catch_up_effort = analyzer.calculate_catch_up_effort(handicap_distance, fitness, race_distance)
        amplified_dq = analyzer.calculate_dq_risk_amplification(handicap_distance, dq_risk, fitness)
        
        handicap_data.append({
            'idx': idx,
            'is_penalized': is_penalized,
            'catch_up_effort': catch_up_effort,
            'amplified_dq': amplified_dq,
        })
    
    # Calculate field-dependent metrics (drafting bonus, threshold edge)
    penalized_count = sum(1 for h in handicap_data if h['is_penalized'])
    
    for pos, h_data in enumerate(handicap_data):
        idx = h_data['idx']
        
        # Count non-penalized horses for drafting (horses before this position)
        num_non_penalized_ahead = sum(
            1 for i in range(pos)
            if not handicap_data[i]['is_penalized']
        )
        
        # Get row data using .loc with index label
        row = df.loc[idx] if idx in df.index else df.iloc[pos]
        
        drafting_bonus = analyzer.calculate_drafting_bonus(
            h_data['is_penalized'],
            num_non_penalized_ahead,
            row.get('S_COEFF', 0.5) if hasattr(row, 'get') else row['S_COEFF'] if 'S_COEFF' in row else 0.5
        )
        
        threshold_edge = analyzer.calculate_threshold_edge_advantage(
            row.get('HORSE_EARNINGS', 0) if hasattr(row, 'get') else row['HORSE_EARNINGS'] if 'HORSE_EARNINGS' in row else 0,
            earnings_threshold,
            penalized_count,
            len(df)
        )
        
        # Overall handicap adjustment to performance
        if h_data['is_penalized']:
            adjustment = 1.0 / h_data['catch_up_effort']  # Inverse of effort
        else:
            adjustment = 1.0 + (drafting_bonus + threshold_edge) / 100
        
        h_data['drafting_bonus'] = drafting_bonus
        h_data['threshold_edge'] = threshold_edge
        h_data['adjustment'] = adjustment
    
    # Add columns to dataframe
    df['IS_PENALIZED'] = [h['is_penalized'] for h in handicap_data]
    df['CATCH_UP_EFFORT'] = [h['catch_up_effort'] for h in handicap_data]
    df['AMPLIFIED_DQ_RISK'] = [h['amplified_dq'] for h in handicap_data]
    df['DRAFTING_BONUS'] = [h['drafting_bonus'] for h in handicap_data]
    df['THRESHOLD_EDGE_ADVANTAGE'] = [h['threshold_edge'] for h in handicap_data]
    df['HANDICAP_ADJUSTED_SCORE'] = [h['adjustment'] for h in handicap_data]
    
    return df


def generate_handicap_prognosis(race_df: pd.DataFrame,
                                 composite_df: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """
    Generate handicap-aware prognosis combining composite score with handicap adjustments.
    
    Args:
        race_df: Race data with handicap analysis columns
        composite_df: Composite score dataframe (optional)
    
    Returns: DataFrame with handicap-adjusted rankings and insights
    """
    if composite_df is None or composite_df.empty:
        return race_df
    
    result = composite_df.copy() if isinstance(composite_df, pd.DataFrame) else pd.DataFrame()
    
    if 'HANDICAP_ADJUSTED_SCORE' not in race_df.columns:
        return result
    
    # Merge handicap data
    if 'N°' in result.columns and 'N°' in race_df.columns:
        race_handicap = race_df[['N°', 'HANDICAP_ADJUSTED_SCORE', 'IS_PENALIZED', 
                                  'CATCH_UP_EFFORT', 'AMPLIFIED_DQ_RISK', 'DRAFTING_BONUS']]
        result = result.merge(race_handicap, on='N°', how='left')
    
    # Apply handicap adjustment to composite score
    if 'Composite' in result.columns and 'HANDICAP_ADJUSTED_SCORE' in result.columns:
        result['Composite_Handicap_Adjusted'] = (
            result['Composite'] * result['HANDICAP_ADJUSTED_SCORE']
        ).round(3)
        result = result.sort_values('Composite_Handicap_Adjusted', ascending=False)
    
    return result


if __name__ == "__main__":
    # Test cases
    print("=" * 60)
    print("HANDICAP MECHANICS - TEST EXAMPLES")
    print("=" * 60)
    
    # Test 1: Extract handicap type
    print("\n1. HANDICAP TYPE EXTRACTION:")
    test_conditions = [
        "Handicap - 25m for horses over €50,000",
        "Handicap (50 mètres) - Class 2",
        "Prix de France - Standard race",
    ]
    
    for cond in test_conditions:
        hc_type = HandicapAnalyzer.extract_handicap_type(cond)
        print(f"   '{cond}' → {hc_type}m")
    
    # Test 2: Extract earnings threshold
    print("\n2. EARNINGS THRESHOLD EXTRACTION:")
    test_thresholds = [
        "for horses that have not won €50,000",
        "Handicap - max earnings: 75,000€",
        "Horses over €100.000",
    ]
    
    for cond in test_thresholds:
        threshold = HandicapAnalyzer.extract_earnings_threshold(cond)
        print(f"   '{cond}' → €{threshold:,.0f}")
    
    # Test 3: Catch-up effort calculation
    print("\n3. CATCH-UP EFFORT MULTIPLIER:")
    fitness_levels = [1, 3, 5, 7, 10]
    for fitness in fitness_levels:
        effort_25 = HandicapAnalyzer.calculate_catch_up_effort(25, fitness)
        effort_50 = HandicapAnalyzer.calculate_catch_up_effort(50, fitness)
        print(f"   Fitness {fitness}: 25m={effort_25}x, 50m={effort_50}x")
    
    # Test 4: DQ Risk amplification
    print("\n4. DISQUALIFICATION RISK AMPLIFICATION:")
    base_risks = [10, 30, 50, 80]
    for base_risk in base_risks:
        risk_25 = HandicapAnalyzer.calculate_dq_risk_amplification(25, base_risk, 5)
        risk_50 = HandicapAnalyzer.calculate_dq_risk_amplification(50, base_risk, 5)
        print(f"   Base {base_risk}: 25m→{risk_25}, 50m→{risk_50}")
    
    print("\n" + "=" * 60)
