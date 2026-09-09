#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Handicap Integration Module for RaceX race_scraper_app.py

This module provides ready-to-use functions that integrate handicap mechanics
into your existing trotting race analysis pipeline.

Drop-in replacement functions for enhanced versions of:
- analyze_trotting_fitness() → analyze_trotting_fitness_with_handicap()
- analyze_trotting_performance() → analyze_trotting_performance_with_handicap()
- analyze_trotting_disqualification_risk() → analyze_trotting_dq_risk_with_handicap()
"""

import pandas as pd
import numpy as np
from typing import Optional


def analyze_trotting_fitness_with_handicap(race_df, race_conditions=''):
    """
    Analyze fitness for trotting races INCLUDING handicap penalty effects.
    
    Extends the original analyze_trotting_fitness() by:
    - Identifying penalized horses (25m or 50m handicap)
    - Adjusting required fitness level based on catch-up effort
    - Flagging horses with poor fitness + heavy handicap (DQ risk)
    
    Returns DataFrame with columns:
    - N°, Cheval, Cote, Fitness (original)
    - HANDICAP_DISTANCE, IS_PENALIZED, CATCH_UP_EFFORT (NEW)
    - FITNESS_ADJUSTED_FOR_HANDICAP (NEW)
    """
    try:
        from model_functions import compute_d_perf
        from handicap_mechanics import analyze_handicap_impact, HandicapAnalyzer
        
        # Get base fitness analysis (existing logic)
        fa_col = 'FA' if 'FA' in race_df.columns else None
        fm_col = 'FM' if 'FM' in race_df.columns else None
        perf_col = 'DERNIÈRES PERF.' if 'DERNIÈRES PERF.' in race_df.columns else None
        
        fitness_col = fa_col if fa_col else fm_col
        disc = 'a' if fa_col else 'm'
        
        cheval_col = 'CHEVAL' if 'CHEVAL' in race_df.columns else ('Cheval' if 'Cheval' in race_df.columns else None)
        cote_col = 'COTE' if 'COTE' in race_df.columns else ('Cote' if 'Cote' in race_df.columns else None)
        num_col = 'N°' if 'N°' in race_df.columns else ('N' if 'N' in race_df.columns else None)
        
        if not cheval_col or not cote_col:
            return pd.DataFrame()
        
        # Add handicap analysis
        race_df_hc = analyze_handicap_impact(race_df, race_conditions)
        
        # Build analysis dataframe
        analysis_data = []
        for idx, row in race_df_hc.iterrows():
            try:
                horse_num = row.get(num_col)
                horse_name = row.get(cheval_col)
                odds = row.get(cote_col)
                
                # Get fitness value
                if fitness_col and fitness_col in race_df.columns:
                    fitness_val = row.get(fitness_col)
                    if pd.notna(fitness_val):
                        fitness_val = pd.to_numeric(fitness_val, errors='coerce')
                        if pd.notna(fitness_val) and fitness_val > 0:
                            analysis_data.append({
                                'N°': horse_num,
                                'Cheval': horse_name,
                                'Cote': odds,
                                'Fitness': fitness_val,
                                'IS_PENALIZED': row.get('IS_PENALIZED', False),
                                'HANDICAP_DISTANCE': row.get('HANDICAP_DISTANCE'),
                                'CATCH_UP_EFFORT': row.get('CATCH_UP_EFFORT', 1.0),
                            })
                elif perf_col and perf_col in race_df.columns:
                    perf_str = row.get(perf_col)
                    if pd.notna(perf_str):
                        d_perf = compute_d_perf(str(perf_str))
                        fitness_val = d_perf.get(disc, 0)
                        if fitness_val and fitness_val > 0:
                            analysis_data.append({
                                'N°': horse_num,
                                'Cheval': horse_name,
                                'Cote': odds,
                                'Fitness': fitness_val,
                                'IS_PENALIZED': row.get('IS_PENALIZED', False),
                                'HANDICAP_DISTANCE': row.get('HANDICAP_DISTANCE'),
                                'CATCH_UP_EFFORT': row.get('CATCH_UP_EFFORT', 1.0),
                            })
            except Exception as e:
                print(f"[DEBUG] Error processing row for fitness: {e}")
                continue
        
        if not analysis_data:
            return pd.DataFrame()
        
        analysis = pd.DataFrame(analysis_data)
        
        # Add fitness adjusted for handicap
        # Higher catch-up effort = needs better fitness, so effective fitness is worse
        analysis['FITNESS_ADJUSTED_FOR_HANDICAP'] = (
            analysis['Fitness'] * analysis['CATCH_UP_EFFORT']
        ).round(2)
        
        # Sort by adjusted fitness ASCENDING (lower = better, considering handicap)
        analysis = analysis.sort_values('FITNESS_ADJUSTED_FOR_HANDICAP', ascending=True)
        
        return analysis
    
    except Exception as e:
        print(f"Error in analyze_trotting_fitness_with_handicap: {e}")
        import traceback
        traceback.print_exc()
        return pd.DataFrame()


def analyze_trotting_performance_with_handicap(race_df, race_conditions=''):
    """
    Analyze success coefficient for trotting races INCLUDING handicap effects.
    
    Extends original analyze_trotting_performance() by:
    - Calculating drafting bonus for penalized horses
    - Adjusting success coefficient for catch-up penalty
    - Showing threshold edge advantage for sub-threshold horses
    
    Returns DataFrame with columns:
    - N°, Cheval, Cote, S_COEFF (original)
    - S_COEFF_Handicap_Adjusted (NEW)
    - DRAFTING_BONUS, THRESHOLD_EDGE_ADVANTAGE (NEW)
    """
    try:
        from model_functions import success_coefficient
        from handicap_mechanics import analyze_handicap_impact
        
        # Add handicap analysis
        race_df_hc = analyze_handicap_impact(race_df, race_conditions)
        
        cheval_col = 'CHEVAL' if 'CHEVAL' in race_df.columns else 'Cheval'
        cote_col = 'COTE' if 'COTE' in race_df.columns else 'Cote'
        num_col = 'N°' if 'N°' in race_df.columns else 'N'
        perf_col = 'DERNIÈRES PERF.' if 'DERNIÈRES PERF.' in race_df.columns else None
        
        # Determine discipline
        discipline = 'a'
        if 'RACE_TYPE' in race_df.columns and 'monté' in str(race_df['RACE_TYPE'].iloc[0]).lower():
            discipline = 'm'
        
        # Build analysis
        analysis_data = []
        for idx, row in race_df_hc.iterrows():
            try:
                horse_num = row.get(num_col)
                horse_name = row.get(cheval_col)
                odds = row.get(cote_col)
                
                # Get success coefficient
                s_coeff = 0.0
                if 'S_COEFF' in race_df.columns:
                    s_coeff = pd.to_numeric(row.get('S_COEFF', 0), errors='coerce') or 0.0
                elif perf_col and pd.notna(row.get(perf_col)):
                    s_coeff = success_coefficient(str(row.get(perf_col)), discipline)
                
                # Get handicap metrics
                is_penalized = row.get('IS_PENALIZED', False)
                catch_up_effort = row.get('CATCH_UP_EFFORT', 1.0)
                drafting_bonus = row.get('DRAFTING_BONUS', 0.0)
                threshold_edge = row.get('THRESHOLD_EDGE_ADVANTAGE', 0.0)
                
                # Adjust S_COEFF for handicap
                # Penalized horses: lower score (harder to succeed)
                # Non-penalized: higher score (advantage)
                if is_penalized:
                    s_coeff_adj = s_coeff / catch_up_effort  # Divided by effort = reduced performance
                else:
                    s_coeff_adj = s_coeff * (1 + (drafting_bonus + threshold_edge) / 100)
                
                analysis_data.append({
                    'N°': horse_num,
                    'Cheval': horse_name,
                    'Cote': odds,
                    'S_COEFF': round(s_coeff, 3),
                    'S_COEFF_Handicap_Adjusted': round(s_coeff_adj, 3),
                    'DRAFTING_BONUS': drafting_bonus,
                    'THRESHOLD_EDGE_ADVANTAGE': threshold_edge,
                    'IS_PENALIZED': is_penalized,
                })
            except Exception as e:
                print(f"[DEBUG] Error processing performance row: {e}")
                continue
        
        if not analysis_data:
            return pd.DataFrame()
        
        analysis = pd.DataFrame(analysis_data)
        
        # Sort by adjusted S_COEFF DESCENDING (higher = better)
        analysis = analysis.sort_values('S_COEFF_Handicap_Adjusted', ascending=False)
        
        return analysis
    
    except Exception as e:
        print(f"Error in analyze_trotting_performance_with_handicap: {e}")
        import traceback
        traceback.print_exc()
        return pd.DataFrame()


def analyze_trotting_dq_risk_with_handicap(race_df, race_conditions=''):
    """
    Analyze disqualification risk INCLUDING handicap amplification.
    
    Extends original analyze_trotting_disqualification_risk() by:
    - Amplifying DQ risk for penalized horses
    - Showing base vs handicap-adjusted risk
    - Flagging high-risk penalized horses (extreme danger zone)
    
    Returns DataFrame with columns:
    - N°, Cheval, DQ_Risk (original)
    - AMPLIFIED_DQ_RISK (NEW)
    - DQ_RISK_INCREASE, RISK_LEVEL (NEW)
    """
    try:
        from handicap_mechanics import analyze_handicap_impact
        
        # Add handicap analysis
        race_df_hc = analyze_handicap_impact(race_df, race_conditions)
        
        cheval_col = 'CHEVAL' if 'CHEVAL' in race_df.columns else 'Cheval'
        num_col = 'N°' if 'N°' in race_df.columns else 'N'
        
        analysis_data = []
        for idx, row in race_df_hc.iterrows():
            try:
                horse_num = row.get(num_col)
                horse_name = row.get(cheval_col)
                
                base_dq = row.get('DQ_Risk', 50)
                amplified_dq = row.get('AMPLIFIED_DQ_RISK', base_dq)
                is_penalized = row.get('IS_PENALIZED', False)
                handicap_distance = row.get('HANDICAP_DISTANCE')
                
                dq_increase = amplified_dq - base_dq
                
                # Risk level classification
                if amplified_dq < 20:
                    risk_level = "Low"
                elif amplified_dq < 40:
                    risk_level = "Moderate"
                elif amplified_dq < 60:
                    risk_level = "High"
                else:
                    risk_level = "Extreme"
                
                analysis_data.append({
                    'N°': horse_num,
                    'Cheval': horse_name,
                    'DQ_Risk_Base': round(base_dq, 2),
                    'DQ_Risk_Amplified': round(amplified_dq, 2),
                    'DQ_RISK_INCREASE': f"+{round(dq_increase, 2)}" if dq_increase > 0 else "None",
                    'RISK_LEVEL': risk_level,
                    'IS_PENALIZED': is_penalized,
                    'HANDICAP_DISTANCE': handicap_distance,
                })
            except Exception as e:
                print(f"[DEBUG] Error processing DQ risk row: {e}")
                continue
        
        if not analysis_data:
            return pd.DataFrame()
        
        analysis = pd.DataFrame(analysis_data)
        
        # Sort by amplified DQ risk DESCENDING (highest risk first)
        analysis = analysis.sort_values('DQ_Risk_Amplified', ascending=False)
        
        return analysis
    
    except Exception as e:
        print(f"Error in analyze_trotting_dq_risk_with_handicap: {e}")
        import traceback
        traceback.print_exc()
        return pd.DataFrame()


def compute_trotting_composite_with_handicap(race_df, composite_df, race_conditions=''):
    """
    Apply handicap adjustments to composite score.
    
    Args:
        race_df: Race dataframe with horse info
        composite_df: Composite score dataframe from compute_prognosis()
        race_conditions: Race conditions text
    
    Returns: Composite dataframe with handicap-adjusted columns added
    
    New columns:
    - Composite_Handicap_Adjusted: Score after handicap adjustment
    - Ranking_Original: Original ranking
    - Ranking_Handicap: New ranking with handicap
    - Ranking_Change: +/- positions after handicap adjustment
    """
    try:
        from handicap_mechanics import generate_handicap_prognosis, analyze_handicap_impact
        
        # Add handicap analysis to race_df
        race_df_hc = analyze_handicap_impact(race_df, race_conditions)
        
        # Generate handicap-adjusted prognosis
        result = generate_handicap_prognosis(race_df_hc, composite_df)
        
        # Add ranking change information
        if 'Composite' in result.columns and 'Composite_Handicap_Adjusted' in result.columns:
            # Original ranking
            result['Ranking_Original'] = result['Composite'].rank(ascending=False).astype(int)
            # New ranking with handicap
            result['Ranking_Handicap'] = result['Composite_Handicap_Adjusted'].rank(ascending=False).astype(int)
            # Change in ranking (positive = moved up)
            result['Ranking_Change'] = result['Ranking_Original'] - result['Ranking_Handicap']
        
        return result
    
    except Exception as e:
        print(f"Error in compute_trotting_composite_with_handicap: {e}")
        import traceback
        traceback.print_exc()
        return composite_df


def format_handicap_analysis_for_display(race_df_hc, include_detailed=False):
    """
    Format handicap analysis for Streamlit display or console output.
    
    Args:
        race_df_hc: Race dataframe with handicap columns from analyze_handicap_impact()
        include_detailed: If True, show all handicap columns; else show summary
    
    Returns: Formatted DataFrame suitable for display
    """
    try:
        display_df = race_df_hc.copy()
        
        # Select columns for display
        if include_detailed:
            cols = [
                'N°', 'CHEVAL', 'FA', 'S_COEFF', 'DQ_Risk',
                'HANDICAP_DISTANCE', 'IS_PENALIZED', 'CATCH_UP_EFFORT',
                'AMPLIFIED_DQ_RISK', 'DRAFTING_BONUS', 'THRESHOLD_EDGE_ADVANTAGE',
                'HANDICAP_ADJUSTED_SCORE'
            ]
        else:
            cols = ['N°', 'CHEVAL', 'IS_PENALIZED', 'CATCH_UP_EFFORT', 'AMPLIFIED_DQ_RISK']
        
        # Keep only available columns
        cols = [c for c in cols if c in display_df.columns]
        display_df = display_df[cols]
        
        # Format numeric columns
        for col in display_df.columns:
            if display_df[col].dtype in ['float64', 'float32']:
                display_df[col] = display_df[col].round(3)
        
        return display_df
    
    except Exception as e:
        print(f"Error formatting handicap analysis: {e}")
        return race_df_hc


if __name__ == "__main__":
    print("Handicap Integration Module for RaceX")
    print("Ready to integrate with race_scraper_app.py")
    print("\nAvailable functions:")
    print("  - analyze_trotting_fitness_with_handicap()")
    print("  - analyze_trotting_performance_with_handicap()")
    print("  - analyze_trotting_dq_risk_with_handicap()")
    print("  - compute_trotting_composite_with_handicap()")
    print("  - format_handicap_analysis_for_display()")
