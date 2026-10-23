import streamlit as st
import subprocess
import time
import pandas as pd
import numpy as np
import os
import re
from kafka.admin import KafkaAdminClient

import matplotlib
matplotlib.use('Agg') 

from matplotlib.figure import Figure
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
from matplotlib.colors import to_rgba
import geopandas as gpd
from matplotlib.patches import Rectangle, Patch, Wedge
import matplotlib.patches as mpatches
from matplotlib.legend_handler import HandlerBase
from matplotlib.ticker import FuncFormatter, MaxNLocator
from pymongo import MongoClient
import base64

# COSTANTI
SURFACES = ["Hard", "Clay", "Grass"]
SURFACE_NAMES = {"Hard": "Cemento", "Clay": "Terra", "Grass": "Erba"}
SURFACE_COLORS = {
    "Hard": "#004aad",  
    "Clay": "#cc4e00",  
    "Grass": "#2e6417"  
}

def get_player_label(name):
    if not name: return ""
    try:
        parts = name.split()
        if len(parts) >= 2:
            return f"{parts[0][0]}. {parts[-1]}".upper()
        return name.upper()
    except:
        return str(name).upper()

# PERSONALIZZAZIONI
class FlagHandler(HandlerBase):
    def create_artists(self, legend, orig_handle,
                       xdescent, ydescent, width, height, fontsize,
                       trans):
        colors = orig_handle
        patches = []
        h = height / 3.0
        
        for i, c in enumerate(colors):
            rect = mpatches.Rectangle(
                xy=(xdescent, ydescent + i * h),
                width=width,
                height=h,
                facecolor=c,
                edgecolor="black",  
                linewidth=0.5,
                transform=trans
            )
            patches.append(rect)
        return patches

# FUNZIONI GRAFICI 

def gradient_bar(ax, x_center, height, width, color_bottom, color_top, y0=0, zorder=3):
    left = x_center - width/2

    rect = Rectangle((left, y0), width, height, facecolor="none",
                     edgecolor="black", linewidth=1.3, zorder=zorder+1)
    ax.add_patch(rect)

    N = 256
    c0 = np.array(to_rgba(color_bottom))
    c1 = np.array(to_rgba(color_top))
    grad = np.linspace(c0, c1, N).reshape(N, 1, 4)

    im = ax.imshow(
        grad,
        extent=(left, left + width, y0, y0 + height),
        origin="lower",
        aspect="auto",
        zorder=zorder,
    )
    im.set_clip_path(rect)

def plot_h2h_wins_by_surface(df, player1, player2):
    # Filtro H2H
    h2h = df[
        ((df["Winner_Name"] == player1) & (df["Loser_Name"] == player2)) |
        ((df["Winner_Name"] == player2) & (df["Loser_Name"] == player1))
    ].copy()

    p1_wins, p2_wins, totals = [], [], []

    for s in SURFACES:
        h2h_s = h2h[h2h["Surface"] == s]
        w1 = (h2h_s["Winner_Name"] == player1).sum()
        w2 = (h2h_s["Winner_Name"] == player2).sum()
        p1_wins.append(w1)
        p2_wins.append(w2)
        totals.append(w1 + w2)

    x = np.arange(len(SURFACES))
    width = 0.35

    fig = Figure(figsize=(10, 6), facecolor="#f9f9f9")
    ax = fig.subplots()

    sinner_bottom, sinner_top = "#0025cc", "#99c5ff"   
    alcaraz_bottom, alcaraz_top = "#457a00", "#99e17a" 
    
    
    for i in range(len(SURFACES)):
        if p1_wins[i] > 0:
            gradient_bar(ax, x_center=x[i] - width/2, height=p1_wins[i], width=width,
                         color_bottom=sinner_bottom, color_top=sinner_top, zorder=3)
        if p2_wins[i] > 0:
            gradient_bar(ax, x_center=x[i] + width/2, height=p2_wins[i], width=width,
                         color_bottom=alcaraz_bottom, color_top=alcaraz_top, zorder=3)

    ax.set_xlim(-0.6, len(SURFACES) - 0.4)

    ax.set_title(
        "NEGLI SCONTRI DIRETTI CHI HA VINTO DI PIÙ PER SUPERFICIE NEL 2025?",
        fontsize=14,
        weight="bold",
        pad=15
    )
    ax.set_ylabel("Numero di vittorie", fontsize=11)
    ax.yaxis.set_major_locator(MaxNLocator(integer=True))
    
    SURFACE_NAMES = {"Hard": "Cemento", "Grass": "Erba", "Clay": "Terra"}
    ax.set_xticks(x)
    ax.set_xticklabels([SURFACE_NAMES.get(s, s) for s in SURFACES], fontsize=12, weight="bold")
    ax.grid(axis="y", linestyle="--", alpha=0.35)

    maxv = max(p1_wins + p2_wins + [1])
    ax.set_ylim(0, maxv * 1.35)

    for i in range(len(SURFACES)):
        total = totals[i]
        if total == 0:
            continue

        p1pct = p1_wins[i] / total * 100
        p2pct = p2_wins[i] / total * 100

        ax.text(x[i] - width/2, p1_wins[i] + maxv*0.05, f"{p1pct:.1f}%",
                ha="center", fontsize=9, weight="bold")
        ax.text(x[i] + width/2, p2_wins[i] + maxv*0.05, f"{p2pct:.1f}%",
                ha="center", fontsize=9, weight="bold")

        if p1_wins[i] > p2_wins[i]:
            best = get_player_label(player1)
        elif p2_wins[i] > p1_wins[i]:
            best = get_player_label(player2)
        else:
            best = "PARI"

        ax.text(x[i], max(p1_wins[i], p2_wins[i]) + maxv*0.2, f"Migliore:\n{best}",
                ha="center", fontsize=9)

    legend_handles = [
        Patch(facecolor=sinner_top, edgecolor="black", label=get_player_label(player1)),
        Patch(facecolor=alcaraz_top, edgecolor="black", label=get_player_label(player2))
    ]
    ax.legend(handles=legend_handles, frameon=False, fontsize=11, loc='upper center', bbox_to_anchor=(0.5, -0.15), ncol=2)

    plt.tight_layout()
    return fig

def plot_4slams_minutes_single_image(df, player1, player2):
    slams = ["Australian Open", "Roland Garros", "Wimbledon", "US Open"]
    slam_title = {
        "Australian Open": "AUSTRALIAN OPEN",
        "Roland Garros": "ROLAND GARROS",
        "Wimbledon": "WIMBLEDON",
        "US Open": "US OPEN"
    }

    slam_colors = {
        "Australian Open": ("#004aad", "#d7fdff"),
        "Roland Garros":   ("#cc4e00", "#ff914d"),
        "Wimbledon":       ("#2e6417", "#7ed957"),
        "US Open":         ("#00167a", "#7ca8f9")
    }

    fig = Figure(figsize=(15, 9), facecolor="#f9f9f9")
    axes = fig.subplots(2, 2)
    axes = axes.flatten()
    
    match_found_any = False

    for ax, slam in zip(axes, slams):
        df_t = df[df["Tourney_Name"] == slam].copy()
        
        def total_minutes_for_player(dft, p):
            as_winner = dft.loc[dft["Winner_Name"] == p, "Minutes"].sum()
            as_loser = dft.loc[dft["Loser_Name"] == p, "Minutes"].sum()
            return float(as_winner + as_loser)

        m1 = total_minutes_for_player(df_t, player1)
        m2 = total_minutes_for_player(df_t, player2)
        
        if m1 > 0 or m2 > 0:
            match_found_any = True

        winner = "N/D"
        finalist = "N/D"
        
        if "Round" in df_t.columns:
            final_match = df_t[df_t["Round"] == "F"]
            if not final_match.empty:
                winner = final_match.iloc[0]["Winner_Name"]
                finalist = final_match.iloc[0]["Loser_Name"]
                winner = get_player_label(winner)
                finalist = get_player_label(finalist)

        mins = [m1, m2]
        x = np.arange(2)

        c1, c2 = slam_colors[slam]
        ax.bar(x[0], mins[0], color=c1, edgecolor="black", linewidth=1.3)
        ax.bar(x[1], mins[1], color=c2, edgecolor="black", linewidth=1.3)

        for i, v in enumerate(mins):
            ax.text(i, v + max(mins + [1]) * 0.03, f"{int(v)} min", ha="center", va="bottom",
                    fontsize=10, weight="bold")

        ax.set_title(slam_title[slam], fontsize=13, weight="bold", pad=10)

        ax.set_xticks(x)
        ax.set_xticklabels([get_player_label(player1), get_player_label(player2)],
                           fontsize=11, weight="bold")
        ax.set_ylabel("Minuti totali nel torneo", fontsize=10)
        ax.grid(axis="y", linestyle="--", alpha=0.35)

        info_text = f"Vincitore: {winner}\nFinalista: {finalist}"
        ax.text(
            0.5, 0.92, info_text,
            transform=ax.transAxes,
            ha="center", va="top",
            fontsize=10, weight="bold",
            bbox=dict(boxstyle="round,pad=0.4", facecolor="white", edgecolor="black", alpha=0.9)
        )

        ymax = max(mins + [1])
        ax.set_ylim(0, ymax * 1.25)

    fig.suptitle(
        f"CHI HA GIOCATO DI PIÙ NEI 4 GRANDI SLAM DEL 2025 TRA SINNER E ALCARAZ?",
        fontsize=15, weight="bold", y=0.98
    )
    
    plt.tight_layout(rect=[0, 0, 1, 0.95])
    
    if not match_found_any:
        pass
        
    return fig

def render_odds_table(metric_data=None):
    data = {
        "EUROBET": [
            {"sinner": 1.80, "alcaraz": 2.75}, # AO
            {"sinner": 2.40, "alcaraz": 2.60}, # RG
            {"sinner": 2.50, "alcaraz": 2.30}, # WI
            {"sinner": 1.80, "alcaraz": 3.25}  # UO
        ],
        "LOTTOMATICA": [
            {"sinner": 1.65, "alcaraz": 3.00},
            {"sinner": 2.50, "alcaraz": 2.25},
            {"sinner": 2.25, "alcaraz": 2.25},
            {"sinner": 1.90, "alcaraz": 3.00}
        ],
        "ODDSJET": [
            {"sinner": 1.73, "alcaraz": 2.38},
            {"sinner": 2.50, "alcaraz": 2.50},
            {"sinner": 2.50, "alcaraz": 2.38},
            {"sinner": 2.20, "alcaraz": 3.00}
        ]
    }
    


    if metric_data and "predictions_2026" in metric_data:
        preds = metric_data["predictions_2026"]
        
        dag_odds = []
        target_tourneys = ["Australian Open", "Roland Garros", "Wimbledon", "US Open"]
        
        for t_target in target_tourneys:
            match = next((p for p in preds if p.get("TORNEO") == t_target), None)
            if match:
                dag_odds.append({
                    "sinner": float(match.get("Q. SINNER", 0.0)),
                    "alcaraz": float(match.get("Q. ALCARAZ", 0.0))
                })
            else:
                dag_odds.append({"sinner": 0.0, "alcaraz": 0.0})
        
        if any(d["sinner"] > 0 for d in dag_odds):
            data["DAG"] = dag_odds

    slams = ["AUSTRALIAN OPEN", "ROLAND GARROS", "WIMBLEDON", "US OPEN"]
    slam_imgs = ["ao.jpeg", "rg.jpeg", "wim.jpeg", "uo.jpeg"]
    base_path = "/app/data"  
    
    def img_to_b64(path):
        possible_paths = [
            f"data/{path}", 
            f"/app/data/{path}", 
            f"/Users/sfero/Desktop/progetto-tennis-2/data/{path}"
        ]
        file_path = None
        for p in possible_paths:
            if os.path.exists(p):
                file_path = p
                break
        
        if not file_path:
            return ""
            
        with open(file_path, "rb") as f:
            return base64.b64encode(f.read()).decode()

    book_colors = {
        "EUROBET": "#0095B6",
        "LOTTOMATICA": "#5F9EA0",
        "ODDSJET": "#2A52BE",
        "DAG": "#1E90FF"  
    }

    # CSS Styles
    st.markdown("""
    <style>
    .odds-table-container {
        font-family: 'Roboto', sans-serif;
        color: white;
        background-color: #1e1e1e;
        padding: 10px;
        border-radius: 10px;
    }
    .odds-header-row {
        display: flex;
        margin-bottom: 10px;
    }
    .odds-header-cell {
        flex: 1;
        background-color: #7FFFD4; /* User requested #7FFFD4 */
        margin: 0 4px;
        padding: 4px;
        border-radius: 8px;
        display: flex;
        align-items: center;
        justify-content: flex-start;
        font-weight: bold;
        color: #101010; /* Dark text for light background */
        text-transform: uppercase;
        font-size: 0.65em;
        overflow: hidden;
        white-space: normal;
        line-height: 1.1;
    }
    .odds-header-cell img {
        width: 35px;
        height: 35px;
        border-radius: 4px;
        margin-right: 8px;
        flex-shrink: 0;
        object-fit: cover;
    }
    .bookmaker-row {
        display: flex;
        align-items: stretch;
        margin-bottom: 10px;
    }
    .bookmaker-name {
        width: 150px;
        /* background-color set inline */
        display: flex;
        align-items: center;
        padding-left: 20px;
        font-weight: bold;
        border-radius: 8px 0 0 8px;
        color: white;
    }
    .odds-cells {
        flex: 1;
        display: flex;
        background-color: #2c2c2c;
        border-radius: 0 8px 8px 0;
        padding: 5px 0;
    }
    .odds-cell-group {
        flex: 1;
        margin: 0 5px;
        display: flex;
        flex-direction: column;
        gap: 5px;
    }
    .odd-box {
        display: flex;
        justify-content: space-between;
        padding: 8px 6px; /* Reduced horizontal padding to fit ALCARAZ */
        border-radius: 6px;
        font-weight: bold;
        font-size: 0.9em;
        color: #000;
        background-color: #C0C0C0; 
    }
    </style>
    """, unsafe_allow_html=True)

    header_html = '<div class="odds-header-row"><div style="width: 150px;"></div>'
    for name, img_file in zip(slams, slam_imgs):
        b64 = img_to_b64(img_file)
        img_tag = f'<img src="data:image/jpeg;base64,{b64}">' if b64 else ""
        header_html += f'<div class="odds-header-cell">{img_tag} {name}</div>'
    header_html += '</div>'

    body_html = ""
    for bookie, odds_list in data.items():
        bk_color = book_colors.get(bookie, "#33b5e5")
        
        row_html = f'<div class="bookmaker-row"><div class="bookmaker-name" style="background-color: {bk_color};">{bookie}</div><div class="odds-cells">'
        
        for odd in odds_list:
            sin = odd["sinner"]
            alc = odd["alcaraz"]
            
            cell_html = (
                f'<div class="odds-cell-group">'
                f'<div class="odd-box">'
                f'<span>SINNER</span><span>{sin:.2f}</span>'
                f'</div>'
                f'<div class="odd-box">'
                f'<span>ALCARAZ</span><span>{alc:.2f}</span>'
                f'</div>'
                f'</div>'
            )
            row_html += cell_html
            
        row_html += '</div></div>'
        body_html += row_html

    full_html = (
        f'<div class="odds-table-container">'
        f'<h3 style="margin:0 0 15px 0;">SLAM – VINCENTE TORNEO</h3>'
        f'{header_html}'
        f'{body_html}'
        f'</div>'
    )
    
    st.markdown(full_html, unsafe_allow_html=True)

def plot_first_serve_bars_clean(df, players):
    req_cols = ["W_ServicePoints", "W_1stIn", "W_1stWon", "L_ServicePoints", "L_1stIn", "L_1stWon"]
    if not all(c in df.columns for c in req_cols):
        return None

    colors = {players[0]: "#5e2697", players[1]: "#b1a1ed"}
    SURFACE_NAMES = {"Hard": "Cemento", "Grass": "Erba", "Clay": "Terra"}

    def build_player_surface_stats(p):
        rows = []
        for s in SURFACES:
            df_s = df[df["Surface"] == s]

            w = df_s[df_s["Winner_Name"] == p][["W_ServicePoints", "W_1stIn", "W_1stWon"]].copy()
            l = df_s[df_s["Loser_Name"] == p][["L_ServicePoints", "L_1stIn", "L_1stWon"]].copy()

            w.columns = ["svpt", "first_in", "first_won"]
            l.columns = ["svpt", "first_in", "first_won"]

            d = pd.concat([w, l], ignore_index=True)

            n_matches = len(d)
            
            d = d.fillna(0)

            if d.empty or d["svpt"].sum() == 0 or d["first_in"].sum() == 0:
                rows.append((0.0, 0.0, n_matches))
                continue

            in_pct = d["first_in"].sum() / d["svpt"].sum()          
            won_pct = d["first_won"].sum() / d["first_in"].sum()    

            rows.append((in_pct, won_pct, n_matches))
        return rows

    stats = {p: build_player_surface_stats(p) for p in players}
    
    fig = Figure(figsize=(14, 6), facecolor="#f9f9f9")
    axes = fig.subplots(1, 2)
    x = np.arange(len(SURFACES))
    width = 0.35

    for i, p in enumerate(players):
        bar_vals = [stats[p][j][2] for j in range(3)]        
        pct_vals = [stats[p][j][0] * 100 for j in range(3)]  

        axes[0].bar(x + (i - 0.5)*width, bar_vals, width,
                    label=get_player_label(p),
                    color=colors[p], edgecolor="black")

        for xi, b, pct in zip(x, bar_vals, pct_vals):
            axes[0].text(xi + (i - 0.5)*width, b + 0.15, f"{pct:.1f}%",
                         ha="center", va="bottom", fontsize=10, weight="bold")

    axes[0].set_title("% PRIME IN CAMPO", fontsize=13, weight="bold")
    axes[0].set_xticks(x)
    axes[0].set_xticklabels([SURFACE_NAMES.get(s,s) for s in SURFACES], weight="bold")
    axes[0].set_ylabel("Numero di partite", fontsize=11)
    axes[0].grid(axis="y", linestyle="--", alpha=0.3)

    for i, p in enumerate(players):
        bar_vals = [stats[p][j][2] for j in range(3)]        
        pct_vals = [stats[p][j][1] * 100 for j in range(3)]  

        axes[1].bar(x + (i - 0.5)*width, bar_vals, width,
                    label=p.split()[-1].upper(),
                    color=colors[p], edgecolor="black")

        for xi, b, pct in zip(x, bar_vals, pct_vals):
            axes[1].text(xi + (i - 0.5)*width, b + 0.15, f"{pct:.1f}%",
                         ha="center", va="bottom", fontsize=10, weight="bold")

    axes[1].set_title("% PUNTI VINTI CON LA PRIMA", fontsize=13, weight="bold")
    axes[1].set_xticks(x)
    axes[1].set_xticklabels([SURFACE_NAMES.get(s,s) for s in SURFACES], weight="bold")
    axes[1].set_ylabel("Numero di partite", fontsize=11)
    axes[1].grid(axis="y", linestyle="--", alpha=0.3)

    max_matches = max([stats[p][j][2] for p in players for j in range(3)] + [1])
    for ax in axes:
        ax.set_ylim(0, max_matches * 1.25)

    fig.suptitle(
        "CHI TRA I DUE HA AVUTO UN SERVIZIO PIÙ EFFICACE NEL 2025?",
        fontsize=15, weight="bold"
    )

    axes[1].legend(frameon=False, fontsize=11)
    plt.tight_layout(rect=[0, 0, 1, 0.93])
    return fig

def plot_first_serve_h2h_scorecard(df, player1, player2):
    h2h = df[
        ((df["Winner_Name"] == player1) & (df["Loser_Name"] == player2)) |
        ((df["Winner_Name"] == player2) & (df["Loser_Name"] == player1))
    ].copy()

    colors = {player1: "#5e2697", player2: "#b1a1ed"} 
    SURFACE_NAMES = {"Hard": "Cemento", "Grass": "Erba", "Clay": "Terra"}
    
    pastel = {
        player1: "#c0c0c0",   
        player2: "#bc9c22",   
        "neutral": "#F2F2F2",
        "header":  "#EFEFEF",
        "text_dark": "#1f1f1f"
    }

    def build_player_surface_stats_h2h(p):
        rows = []
        for s in SURFACES:
            df_s = h2h[h2h["Surface"] == s]

            w = df_s[df_s["Winner_Name"] == p][["W_ServicePoints", "W_1stIn", "W_1stWon"]].copy()
            l = df_s[df_s["Loser_Name"] == p][["L_ServicePoints", "L_1stIn", "L_1stWon"]].copy()

            w.columns = ["svpt", "first_in", "first_won"]
            l.columns = ["svpt", "first_in", "first_won"]

            d = pd.concat([w, l], ignore_index=True)
            d = d.fillna(0) 

            n_matches = len(df_s[df_s["Winner_Name"].notna()]) 

            if d.empty or d["svpt"].sum() == 0 or d["first_in"].sum() == 0:
                rows.append((0.0, 0.0, n_matches))
                continue

            in_pct = d["first_in"].sum() / d["svpt"].sum()
            won_pct = d["first_won"].sum() / d["first_in"].sum()

            rows.append((in_pct, won_pct, n_matches))
        return rows

    stats = {
        player1: build_player_surface_stats_h2h(player1),
        player2: build_player_surface_stats_h2h(player2)
    }

    def cell_bg_and_delta(v1, v2, label_a, label_b, eps=1e-9):
        diff = v1 - v2
        if abs(diff) <= eps:
            return pastel["neutral"], None

        if diff > 0:
            return pastel[player1], f"Δ {label_a}: +{abs(diff):.1f}%"
        else: 
            return pastel[player2], f"Δ {label_b}: +{abs(diff):.1f}%"

    row_labels = ["", "% PRIME IN CAMPO", "% PUNTI VINTI CON LA PRIMA", "MATCH H2H"]
    n_rows = 4
    n_cols = 1 + len(SURFACES)

    fig = Figure(figsize=(14, 5), facecolor="#f9f9f9")
    ax = fig.subplots()
    ax.set_axis_off()

    left, bottom, width, height = 0.03, 0.08, 0.94, 0.82
    cell_w = width / n_cols
    cell_h = height / n_rows

    fig.suptitle(
        "QUALITÀ DELLA PRIMA DI SERVIZIO NEGLI SCONTRI DIRETTI DEL 2025",
        fontsize=16, weight="bold", y=0.98
    )
 
    for r in range(n_rows):
        for c in range(n_cols):
            x0 = left + c * cell_w
            y0 = bottom + (n_rows - 1 - r) * cell_h

            face = "white"
            if r == 0 and c > 0:
                face = pastel["header"]
            if c == 0 and r > 0:
                face = pastel["header"]

            ax.add_patch(Rectangle((x0, y0), cell_w, cell_h,
                                   facecolor=face, edgecolor="black", linewidth=1.0))

    for j, s in enumerate(SURFACES, start=1):
        ax.text(left + j*cell_w + cell_w/2,
                bottom + (n_rows-1)*cell_h + cell_h/2,
                SURFACE_NAMES.get(s, s),
                ha="center", va="center",
                fontsize=12, weight="bold")

    for r in range(1, n_rows):
        ax.text(left + cell_w/2,
                bottom + (n_rows-1-r)*cell_h + cell_h/2,
                row_labels[r],
                ha="center", va="center",
                fontsize=10, weight="bold")  

    p1lab = get_player_label(player1)
    p2lab = get_player_label(player2)

    for j, s in enumerate(SURFACES):
        c = j + 1

        in1 = stats[player1][j][0] * 100
        in2 = stats[player2][j][0] * 100
        won1 = stats[player1][j][1] * 100
        won2 = stats[player2][j][1] * 100
        nmatch = stats[player1][j][2]

        r = 1
        bg, delta_text = cell_bg_and_delta(in1, in2, p1lab, p2lab)
        x0 = left + c*cell_w
        y0 = bottom + (n_rows-1-r)*cell_h
        ax.add_patch(Rectangle((x0, y0), cell_w, cell_h,
                               facecolor=bg, edgecolor="black", linewidth=1.0))

        ax.text(x0 + cell_w/2, y0 + cell_h*0.64,
                f"{p1lab}: {in1:.1f}%",
                ha="center", va="center", fontsize=11, weight="bold", color=pastel["text_dark"])
        ax.text(x0 + cell_w/2, y0 + cell_h*0.36,
                f"{p2lab}: {in2:.1f}%",
                ha="center", va="center", fontsize=11, weight="bold", color=pastel["text_dark"])

        if delta_text is not None:
            ax.text(x0 + cell_w/2, y0 + cell_h*0.12,
                    delta_text,
                    ha="center", va="center", fontsize=10)

        r = 2
        bg, delta_text = cell_bg_and_delta(won1, won2, p1lab, p2lab)
        x0 = left + c*cell_w
        y0 = bottom + (n_rows-1-r)*cell_h
        ax.add_patch(Rectangle((x0, y0), cell_w, cell_h,
                               facecolor=bg, edgecolor="black", linewidth=1.0))

        ax.text(x0 + cell_w/2, y0 + cell_h*0.64,
                f"{p1lab}: {won1:.1f}%",
                ha="center", va="center", fontsize=11, weight="bold", color=pastel["text_dark"])
        ax.text(x0 + cell_w/2, y0 + cell_h*0.36,
                f"{p2lab}: {won2:.1f}%",
                ha="center", va="center", fontsize=11, weight="bold", color=pastel["text_dark"])

        if delta_text is not None:
            ax.text(x0 + cell_w/2, y0 + cell_h*0.12,
                    delta_text,
                    ha="center", va="center", fontsize=10)

        r = 3
        x0 = left + c*cell_w
        y0 = bottom + (n_rows-1-r)*cell_h
        ax.text(x0 + cell_w/2, y0 + cell_h/2,
                f"{nmatch}",
                ha="center", va="center", fontsize=12, weight="bold")

    legend_handles = [
        Patch(facecolor=pastel[player1], edgecolor="black", label=p1lab),
        Patch(facecolor=pastel[player2], edgecolor="black", label=p2lab)
        ]
    
    ax.legend(
        handles=legend_handles,
        loc="lower center",
        bbox_to_anchor=(0.5, -0.08),
        ncol=2,
        frameon=False,
        fontsize=11
        )

    return fig


def plot_h2h_ace_df_bars_horizontal_per_match(df, player1, player2):
    h2h = df[
        ((df["Winner_Name"] == player1) & (df["Loser_Name"] == player2)) |
        ((df["Winner_Name"] == player2) & (df["Loser_Name"] == player1))
    ].copy()
    if "Tourney_Date" in h2h.columns:
        h2h = h2h.sort_values("Tourney_Date")
    
    needed = ["W_ServicePoints", "W_Ace", "W_DoubleFault", "L_ServicePoints", "L_Ace", "L_DoubleFault"]
    for col in needed:
        if col not in h2h.columns:
            h2h[col] = 0

    colors = {
        player1: "#ffc2c2",
        player2: "#ff1fdd"
    }

    n_matches = len(h2h)

    def match_stats_abs_and_pct(row, p):
        def safe_float(x):
            try: return float(x)
            except: return 0.0

        if row["Winner_Name"] == p:
            svpt = safe_float(row["W_ServicePoints"])
            ace  = safe_float(row["W_Ace"])
            dff  = safe_float(row["W_DoubleFault"])
        else:
            svpt = safe_float(row["L_ServicePoints"])
            ace  = safe_float(row["L_Ace"])
            dff  = safe_float(row["L_DoubleFault"])

        if svpt > 0:
            ace_pct = ace / svpt * 100
            df_pct  = dff / svpt * 100
        else:
            ace_pct = 0.0
            df_pct  = 0.0

        return ace_pct, df_pct

    ncols = 3
    nrows = int(np.ceil(n_matches / ncols))
    nrows = max(1, nrows)

    fig = Figure(figsize=(6.2 * ncols, 3.8 * nrows), facecolor="#f9f9f9")
    axes = fig.subplots(nrows, ncols)
    if nrows * ncols > 1:
        axes = np.array(axes).reshape(-1)
    else:
        axes = np.array([axes])

    metrics = ["% ACE", "% DOPPI FALLI"]
    y = np.arange(len(metrics))
    bar_h = 0.33

    XMAX = 18
    XTICKS = np.arange(0, XMAX + 1, 3)

    for idx, (_, row) in enumerate(h2h.iterrows()):
        ax = axes[idx]

        p1_ace_pct, p1_df_pct = match_stats_abs_and_pct(row, player1)
        p2_ace_pct, p2_df_pct = match_stats_abs_and_pct(row, player2)

        p1_vals = [p1_ace_pct, p1_df_pct]
        p2_vals = [p2_ace_pct, p2_df_pct]

        ax.set_xlim(0, XMAX)
        ax.set_xticks(XTICKS)

        ax.barh(
            y - bar_h/2, p1_vals, height=bar_h,
            color=colors[player1], edgecolor="black"
        )
        ax.barh(
            y + bar_h/2, p2_vals, height=bar_h,
            color=colors[player2], edgecolor="black"
        )

        def label_bar(val, y_pos):
            ax.text(
                min(val + 0.4, XMAX - 0.2),
                y_pos,
                f"{val:.2f}%",
                va="center",
                ha="left" if val < XMAX - 1 else "right",
                fontsize=9,
                weight="bold",
                clip_on=True
            )

        for i in range(len(metrics)):
            label_bar(p1_vals[i], y[i] - bar_h/2)
            label_bar(p2_vals[i], y[i] + bar_h/2)

        ax.set_yticks(y)
        ax.set_yticklabels(metrics, fontsize=10, weight="bold")
        ax.grid(axis="x", linestyle="--", alpha=0.35)
        ax.set_xlabel("Percentuale (%)")
        ax.invert_yaxis()

        title_parts = []
        if "Tourney_Name" in h2h.columns:
            title_parts.append(str(row["Tourney_Name"]))
        if "Round" in h2h.columns:
            title_parts.append(str(row["Round"]))
        if "Surface" in h2h.columns:
            title_parts.append(str(row["Surface"]))

        subtitle = " | ".join([t for t in title_parts if t and t != "nan"])
        ax.set_title(
            f"Match {idx+1}" + (f"\n{subtitle}" if subtitle else ""),
            fontsize=12,
            weight="bold"
        )

    for j in range(n_matches, len(axes)):
        axes[j].axis("off")

    fig.suptitle(
        "%ACE E %DOPPI FALLI NEGLI SCONTRI DIRETTI DEL 2025",
        fontsize=17,
        weight="bold",
        y=0.975
    )

    fig.legend(
        handles=[
            Patch(facecolor=colors[player1], edgecolor="black", label=get_player_label(player1)),
            Patch(facecolor=colors[player2], edgecolor="black", label=get_player_label(player2))
        ],
        loc="upper left",
        bbox_to_anchor=(0.01, 0.99),
        frameon=False,
        fontsize=12
    )

    fig.subplots_adjust(wspace=0.35, hspace=0.65, top=0.80, bottom=0.11)
    
    return fig


def plot_ace_df_four_area_charts_all_matches(df, player1, player2):
    players = [player1, player2]

    ACE_GREEN = "#32CD32"
    DF_RED = "#E53935"

    series = {player1: {"ace": [], "df": []}, player2: {"ace": [], "df": []}}

    def safe_float(x):
        try: return float(x)
        except: return 0.0

    for _, row in df.iterrows():
        for p in players:
            if row["Winner_Name"] == p:
                svpt = safe_float(row.get("W_ServicePoints", 0))
                ace = safe_float(row.get("W_Ace", 0))
                dff = safe_float(row.get("W_DoubleFault", 0))
            elif row["Loser_Name"] == p:
                svpt = safe_float(row.get("L_ServicePoints", 0))
                ace = safe_float(row.get("L_Ace", 0))
                dff = safe_float(row.get("L_DoubleFault", 0))
            else:
                continue

            date = row.get("Tourney_Date")

            if svpt <= 0:
                continue

            series[p]["ace"].append((date, ace / svpt * 100))
            series[p]["df"].append((date, dff / svpt * 100))

    def sort_key(x):
        return x[0] if x[0] is not None else "0" 

    for p in players:
        series[p]["ace"] = sorted(series[p]["ace"], key=sort_key)
        series[p]["df"] = sorted(series[p]["df"], key=sort_key)

    def get_vals(p, metric):
        return np.array([v for _, v in series[p][metric]], dtype=float)

    s_ace = get_vals(player1, "ace")
    s_df = get_vals(player1, "df")
    a_ace = get_vals(player2, "ace")
    a_df = get_vals(player2, "df")

    if len(s_ace) == 0 and len(a_ace) == 0:
        return None

    all_values = np.concatenate([s_ace, s_df, a_ace, a_df])
    ymax = all_values.max() * 1.25 if len(all_values) else 1

    fig = Figure(figsize=(16, 10), facecolor="white")
    axes = fig.subplots(4, 1)

    for ax in axes:
        ax.set_facecolor("white")
        ax.grid(axis="y", linestyle="--", alpha=0.25)
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.set_ylim(0, ymax)

    def area_plot(ax, y, color, title, fix_xlim=False):
        x = np.arange(len(y))
        ax.fill_between(x, 0, y, color=color, alpha=0.55)
        ax.plot(x, y, color="black", linewidth=1.2)
        ax.set_title(title, fontsize=13, weight="bold", y=0.9)
        ax.set_ylabel("Percentuale (%)")
        if fix_xlim and len(y) > 0:
            ax.set_xlim(0, len(y) - 1)
        elif len(y) == 0:
            pass

    p1lab = get_player_label(player1)
    p2lab = get_player_label(player2)

    area_plot(axes[0], s_ace, ACE_GREEN, f"{p1lab}")
    area_plot(axes[1], s_df, DF_RED, f"{p1lab}")
    area_plot(axes[2], a_ace, ACE_GREEN, f"{p2lab}", fix_xlim=True)
    area_plot(axes[3], a_df, DF_RED, f"{p2lab}", fix_xlim=True)

    axes[3].set_xlabel("Match (in ordine cronologico)")

    fig.suptitle(
        "ANDAMENTO DEGLI ACE E DOPPI FALLI DEL 2025 DI SINNER E ALCARAZ",
        fontsize=16,
        weight="bold",
        y=0.99
    )

    legend_handles = [
        Patch(facecolor=ACE_GREEN, edgecolor="black", label="ACE%"),
        Patch(facecolor=DF_RED, edgecolor="black", label="Doppi falli %")
    ]

    fig.legend(
        handles=legend_handles,
        loc="upper center",
        ncol=2,
        frameon=False,
        fontsize=12,
        bbox_to_anchor=(0.5, 0.96)
    )

    plt.tight_layout(rect=[0, 0, 1, 0.95], h_pad=3.0)
    return fig


def plot_wins_by_sets_percentage(df, players):
    needed_cols = ["Winner_Name", "Score", "Best_of"] 
    if not all(c in df.columns for c in needed_cols):
        return None

    def sets_played_from_score(score):
        if score is None or (isinstance(score, float) and np.isnan(score)):
            return None

        s = str(score).upper().strip()
        if "W/O" in s or "WO" == s or "RET" in s:
            return None

        tokens = s.split()
        count = 0
        for t in tokens:
            base = t.split("(")[0]
            if "-" in base and base.replace("-", "").isdigit():
                count += 1
        return count if count > 0 else None

    player1, player2 = players[0], players[1]
    
    bo3_pct = {p: [0.0, 0.0] for p in players}
    bo5_pct = {p: [0.0, 0.0, 0.0] for p in players}

    bo3_cnt = {p: [0, 0] for p in players}        
    bo5_cnt = {p: [0, 0, 0] for p in players}    

    match_found = False

    for p in players:
        wins = df[df["Winner_Name"] == p].copy()
        if wins.empty:
            continue
            
        wins["_Sets"] = wins["Score"].apply(sets_played_from_score)
        
        wins["_BO"] = pd.to_numeric(wins["Best_of"], errors='coerce').fillna(0).astype(int)

        w3 = wins[(wins["_BO"] == 3) & (wins["_Sets"].isin([2, 3]))]
        tot3 = len(w3)
        if tot3 > 0:
            match_found = True
            c2 = int((w3["_Sets"] == 2).sum())
            c3 = int((w3["_Sets"] == 3).sum())
            bo3_cnt[p] = [c2, c3]
            bo3_pct[p] = [c2 / tot3 * 100, c3 / tot3 * 100]

        w5 = wins[(wins["_BO"] == 5) & (wins["_Sets"].isin([3, 4, 5]))]
        tot5 = len(w5)
        if tot5 > 0:
            match_found = True
            c3 = int((w5["_Sets"] == 3).sum())
            c4 = int((w5["_Sets"] == 4).sum())
            c5 = int((w5["_Sets"] == 5).sum())
            bo5_cnt[p] = [c3, c4, c5]
            bo5_pct[p] = [c3 / tot5 * 100, c4 / tot5 * 100, c5 / tot5 * 100]

    fig = Figure(figsize=(14, 6), facecolor="#f9f9f9")
    axes = fig.subplots(1, 2)
    width = 0.35

    flag_colors = {
        "Jannik Sinner": ["green", "white", "red"],
        "Carlos Alcaraz": ["#D62828", "#FFD700", "#D62828"]
    }

    def draw_flag_bars(ax, x_pos, counts, player_name, bar_width):
        colors = flag_colors.get(player_name, ["grey", "grey", "grey"])
        h_band = counts / 3.0
        
        ax.bar(x_pos, h_band, bar_width, 
               color=colors[0], edgecolor="black", linewidth=0.5)
        ax.bar(x_pos, h_band, bar_width, bottom=h_band, 
               color=colors[1], edgecolor="black", linewidth=0.5)
        ax.bar(x_pos, counts - 2*h_band, bar_width, bottom=2*h_band, 
               color=colors[2], edgecolor="black", linewidth=0.5)

    ax = axes[0]
    labels3 = ["Vinte in 2 set", "Vinte in 3 set"]
    x = np.arange(len(labels3))
    for i, p in enumerate(players):
        draw_flag_bars(ax, x + (i - 0.5)*width, np.array(bo3_cnt[p]), p, width)
        for xi, c, pct in zip(x, bo3_cnt[p], bo3_pct[p]):
            if c > 0:
                ax.text(xi + (i - 0.5)*width, c + 0.2, f"{pct:.1f}%",
                        ha="center", va="bottom", fontsize=10, weight="bold")

    ax.set_title("VITTORIE NEI MATCH BEST-OF-3", fontsize=13, weight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(labels3, weight="bold")
    ax.set_ylabel("Numero di partite")
    ax.grid(axis="y", linestyle="--", alpha=0.3)

    ax = axes[1]
    labels5 = ["Vinte in 3 set", "Vinte in 4 set", "Vinte in 5 set"]
    x = np.arange(len(labels5))
    for i, p in enumerate(players):
        draw_flag_bars(ax, x + (i - 0.5)*width, np.array(bo5_cnt[p]), p, width)
        for xi, c, pct in zip(x, bo5_cnt[p], bo5_pct[p]):
             if c > 0:
                ax.text(xi + (i - 0.5)*width, c + 0.2, f"{pct:.1f}%",
                        ha="center", va="bottom", fontsize=10, weight="bold")

    ax.set_title("VITTORIE NEI MATCH BEST-OF-5", fontsize=13, weight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(labels5, weight="bold")
    ax.set_ylabel("Numero di partite")
    ax.grid(axis="y", linestyle="--", alpha=0.3)

    max_count = max(
        [bo3_cnt[p][k] for p in players for k in range(2)] +
        [bo5_cnt[p][k] for p in players for k in range(3)] +
        [1]
    )
    axes[0].set_ylim(0, max_count * 1.35)
    axes[1].set_ylim(0, max_count * 1.35)

    fig.suptitle(
        "CHI HA VINTO DI PIÙ COL MINOR NUMERO DI SET GIOCATI NEL 2025 TRA SINNER E ALCARAZ?",
        fontsize=15, weight="bold"
    )

    custom_handles = [
        flag_colors.get("Jannik Sinner", ["grey"]),    
        flag_colors.get("Carlos Alcaraz", ["grey"])    
    ]
    custom_labels = [get_player_label(p) for p in players]

    axes[1].legend(
        handles=custom_handles, 
        labels=custom_labels, 
        handler_map={list: FlagHandler()}, 
        frameon=False, 
        fontsize=11
    )

    plt.tight_layout(rect=[0, 0, 1, 0.93])
    return fig


def plot_win_loss_indoor_outdoor_counts(df, players):
    needed_cols = ["Indoor_Outdoor", "Winner_Name", "Loser_Name"]
    if not all(c in df.columns for c in needed_cols):
        return None

    envs = ["I", "O"]
    env_name = {"I": "INDOOR", "O": "OUTDOOR"}

    win_colors = {
        players[0]: "#2e6417",  
        players[1]: "#7CFC90"  
    }
    loss_color = "#9a9a9a"

    W = {p: [] for p in players}
    L = {p: [] for p in players}

    match_found = False

    for e in envs:
        df_e = df[df["Indoor_Outdoor"].astype(str).str.strip().str.upper() == e]
        for p in players:
            w = (df_e["Winner_Name"] == p).sum()
            l = (df_e["Loser_Name"] == p).sum()
            W[p].append(int(w))
            L[p].append(int(l))
            
            if w > 0 or l > 0:
                match_found = True

    if not match_found:
        pass

    Wpct = {p: [] for p in players}
    Lpct = {p: [] for p in players}
    for i in range(len(envs)):
        for p in players:
            t = W[p][i] + L[p][i]
            if t > 0:
                Wpct[p].append(W[p][i] / t * 100)
                Lpct[p].append(L[p][i] / t * 100)
            else:
                Wpct[p].append(0.0)
                Lpct[p].append(0.0)

    x = np.arange(len(envs))
    width = 0.35

    x = np.arange(len(envs))
    width = 0.35

    fig = Figure(figsize=(11, 6), facecolor="#f9f9f9")
    ax = fig.subplots()

    for i, p in enumerate(players):
        xpos = x + (i - 0.5) * width
        wins_vals = W[p]
        loss_vals = L[p]

        ax.bar(xpos, wins_vals, width,
               color=win_colors[p], edgecolor="black", linewidth=1.2,
               label=f"{get_player_label(p)} - Vittorie")

        ax.bar(xpos, loss_vals, width, bottom=wins_vals,
               color=loss_color, edgecolor="black", linewidth=1.2,
               label=f"{get_player_label(p)} - Sconfitte")

        for j, (xi, wv, lv) in enumerate(zip(xpos, wins_vals, loss_vals)):
            total = wv + lv
            if total == 0:
                continue

            if wv > 0:
                ax.text(xi, wv / 2, f"{Wpct[p][j]:.1f}%",
                        ha="center", va="center", fontsize=10, weight="bold")

            if lv > 0:
                ax.text(xi, wv + lv / 2, f"{Lpct[p][j]:.1f}%",
                        ha="center", va="center", fontsize=7, weight="bold")

    ax.set_title(
        f"CHI HA VINTO DI PIÙ IN INDOOR O OUTDOOR NEL 2025 TRA SINNER E ALCARAZ?",
        fontsize=14, weight="bold", pad=14
    )
    ax.set_ylabel("Numero di partite", fontsize=11)
    ax.set_xticks(x)
    ax.set_xticklabels([env_name[e] for e in envs], fontsize=12, weight="bold")
    ax.grid(axis="y", linestyle="--", alpha=0.35)

    max_val_calc = [W[p][k] + L[p][k] for p in players for k in range(len(envs))]
    max_total = max(max_val_calc) if max_val_calc else 0
    ax.set_ylim(0, max(max_total * 1.2, 5)) # min height 5

    legend_items = [
        Patch(facecolor=win_colors[players[0]], edgecolor="black", label=f"{get_player_label(players[0])} - Vittorie"),
        Patch(facecolor=win_colors[players[1]], edgecolor="black", label=f"{get_player_label(players[1])} - Vittorie"),
        Patch(facecolor=loss_color, edgecolor="black", label="Sconfitte"),
    ]
    ax.legend(handles=legend_items, frameon=False, fontsize=10, ncol=2)

    plt.tight_layout()
    return fig


def _bp_totals_for_player(dft, p):
    needed = ["W_BreakPointSaved", "W_BreakPointFaced", "L_BreakPointSaved", "L_BreakPointFaced"]
    if not all(c in dft.columns for c in needed):
        return 0.0, 0.0, 0.0, 0.0

    w_srv = dft.loc[dft["Winner_Name"] == p, ["W_BreakPointSaved", "W_BreakPointFaced"]].copy()
    l_srv = dft.loc[dft["Loser_Name"] == p,  ["L_BreakPointSaved", "L_BreakPointFaced"]].copy()
    w_srv.columns = ["saved", "faced"]
    l_srv.columns = ["saved", "faced"]
    srv = pd.concat([w_srv, l_srv], ignore_index=True)
    srv = srv.fillna(0)

    saved = float(srv["saved"].sum())
    faced = float(srv["faced"].sum())

    w_ret = dft.loc[dft["Winner_Name"] == p, ["L_BreakPointSaved", "L_BreakPointFaced"]].copy()
    l_ret = dft.loc[dft["Loser_Name"] == p,  ["W_BreakPointSaved", "W_BreakPointFaced"]].copy()
    w_ret.columns = ["opp_saved", "opp_faced"]
    l_ret.columns = ["opp_saved", "opp_faced"]
    ret = pd.concat([w_ret, l_ret], ignore_index=True)
    ret = ret.fillna(0)

    opp_saved = float(ret["opp_saved"].sum())
    opp_faced = float(ret["opp_faced"].sum())

    conv = max(0.0, opp_faced - opp_saved)
    opps = opp_faced

    return saved, faced, conv, opps

def plot_breakpoints_violin(df, players):
    p1, p2 = players[0], players[1]
    
    needed = ["W_BreakPointSaved", "W_BreakPointFaced", "L_BreakPointSaved", "L_BreakPointFaced"]
    if not all(c in df.columns for c in needed):
        return None

    colors = {p1: "#ab9047", p2: "#ffec3d"}
    metrics = ["BP SALVATI", "BP CONVERTITI"]
    x_base = np.arange(len(metrics), dtype=float)
    offset = 0.20

    def per_match_bp_pcts(dft, p):
        d = dft[(dft["Winner_Name"] == p) | (dft["Loser_Name"] == p)].copy()
        saved_pcts = []
        conv_pcts = []
        
        if d.empty:
            return np.array([], dtype=float), np.array([], dtype=float)

        for _, row in d.iterrows():
            if row["Winner_Name"] == p:
                faced = float(row.get("W_BreakPointFaced", 0) or 0)
                saved = float(row.get("W_BreakPointSaved", 0) or 0)

                opp_faced = float(row.get("L_BreakPointFaced", 0) or 0)
                opp_saved = float(row.get("L_BreakPointSaved", 0) or 0)
            else:
                faced = float(row.get("L_BreakPointFaced", 0) or 0)
                saved = float(row.get("L_BreakPointSaved", 0) or 0)

                opp_faced = float(row.get("W_BreakPointFaced", 0) or 0)
                opp_saved = float(row.get("W_BreakPointSaved", 0) or 0)

            if faced > 0:
                saved_pcts.append(saved / faced * 100)

            if opp_faced > 0:
                conv = max(0.0, opp_faced - opp_saved)
                conv_pcts.append(conv / opp_faced * 100)

        return np.array(saved_pcts, dtype=float), np.array(conv_pcts, dtype=float)

    s1_saved, s1_conv = per_match_bp_pcts(df, p1)
    s2_saved, s2_conv = per_match_bp_pcts(df, p2)

    out = {}
    for p in players:
        saved, faced, conv, opps = _bp_totals_for_player(df, p)
        saved_pct = (saved / faced * 100) if faced > 0 else 0.0
        conv_pct = (conv / opps * 100) if opps > 0 else 0.0
        out[p] = {
            "saved": saved, "faced": faced, "saved_pct": saved_pct,
            "conv": conv, "opps": opps, "conv_pct": conv_pct
        }

    fig = Figure(figsize=(12, 6), facecolor="#f9f9f9")
    ax = fig.subplots()
    ax.set_facecolor("#f9f9f9")

    data_by_metric = {
        "BP SALVATI": {p1: s1_saved, p2: s2_saved},
        "BP CONVERTITI": {p1: s1_conv,  p2: s2_conv}
    }

    def draw_violin(values, pos, color):
        if len(values) == 0:
            return None
        vp = ax.violinplot([values], positions=[pos], widths=0.22,
                           showmeans=False, showmedians=True, showextrema=True)
        for b in vp["bodies"]:
            b.set_facecolor(color)
            b.set_edgecolor("black")
            b.set_alpha(0.75)
        for k in ["cmedians", "cmins", "cmaxes", "cbars"]:
            if k in vp:
                vp[k].set_color("black")
                vp[k].set_linewidth(1.2)
        return vp

    for j, m in enumerate(metrics):
        draw_violin(data_by_metric[m][p1], x_base[j] - offset, colors[p1])
        draw_violin(data_by_metric[m][p2], x_base[j] + offset, colors[p2])

        if m == "BP SALVATI":
            t1 = f'{out[p1]["saved_pct"]:.1f}% ({int(out[p1]["saved"])}/{int(out[p1]["faced"])})'
            t2 = f'{out[p2]["saved_pct"]:.1f}% ({int(out[p2]["saved"])}/{int(out[p2]["faced"])})'
        else:
            t1 = f'{out[p1]["conv_pct"]:.1f}% ({int(out[p1]["conv"])}/{int(out[p1]["opps"])})'
            t2 = f'{out[p2]["conv_pct"]:.1f}% ({int(out[p2]["conv"])}/{int(out[p2]["opps"])})'
        y_txt = 101
        ax.text(x_base[j] - offset, y_txt, t1, ha="center", va="bottom", fontsize=10, weight="bold")
        ax.text(x_base[j] + offset, y_txt, t2, ha="center", va="bottom", fontsize=10, weight="bold")

    fig.suptitle("L'IMPORTANZA DELLA PALLA BREAK NEL 2025 PER I DUE TOP PLAYER",
                 fontsize=14, weight="bold", y=0.98)

    ax.set_ylabel("Percentuale (%)", fontsize=11)
    ax.set_xticks(x_base)
    ax.set_xticklabels(metrics, fontsize=11, weight="bold")
    
    ax.set_ylim(-10, 115)
    ax.set_yticks([0, 20, 40, 60, 80, 100])
    
    ax.grid(axis="y", linestyle="--", alpha=0.35)

    legend_items = [
        Patch(facecolor=colors[p1], edgecolor="black", label=get_player_label(p1)),
        Patch(facecolor=colors[p2], edgecolor="black", label=get_player_label(p2))
    ]
    
    fig.legend(
        handles=legend_items,
        loc="lower center",
        ncol=2,
        frameon=False,
        fontsize=11,
        bbox_to_anchor=(0.5, 0.02)
        )
    
    plt.tight_layout(rect=[0, 0.08, 1, 0.93])
    return fig


def plot_breakpoints_h2h_dumbbell(df, players):
    player1, player2 = players[0], players[1]
    
    h2h = df[
        ((df["Winner_Name"] == player1) & (df["Loser_Name"] == player2)) |
        ((df["Winner_Name"] == player2) & (df["Loser_Name"] == player1))
    ].copy()

    s1, f1, c1, o1 = _bp_totals_for_player(h2h, player1)
    s2, f2, c2, o2 = _bp_totals_for_player(h2h, player2)

    s1pct = (s1 / f1 * 100) if f1 > 0 else 0.0
    s2pct = (s2 / f2 * 100) if f2 > 0 else 0.0
    c1pct = (c1 / o1 * 100) if o1 > 0 else 0.0
    c2pct = (c2 / o2 * 100) if o2 > 0 else 0.0

    metrics = ["BP SALVATI", "BP CONVERTITI"]
    y = np.arange(len(metrics))

    
    p1_x = [f1, o1]
    p2_x = [f2, o2]

    p1_txt = [f"{s1pct:.1f}%", f"{c1pct:.1f}%"]
    p2_txt = [f"{s2pct:.1f}%", f"{c2pct:.1f}%"]

    colors = {player1: "#192064", player2: "#3242ca"}


    fig = Figure(figsize=(11, 5), facecolor="#f9f9f9")
    ax = fig.subplots()

    for i in range(len(metrics)):
        ax.plot([p1_x[i], p2_x[i]], [y[i], y[i]],
                linewidth=4, alpha=0.25, color="gray", zorder=1)

    ax.scatter(p1_x, y, s=180, zorder=3, color=colors[player1],
               edgecolor="black", label=get_player_label(player1))
    ax.scatter(p2_x, y, s=180, zorder=3, color=colors[player2],
               edgecolor="black", label=get_player_label(player2))

    max_val = max(p1_x + p2_x + [1])
    ax.set_xlim(0, max_val * 1.35)

    ax.set_yticks(y)
    ax.set_yticklabels([m + " %" for m in metrics], fontsize=12, weight="bold")
    ax.invert_yaxis()

    ax.set_xlabel("Numero di palle break", fontsize=12)
    ax.grid(axis="x", linestyle="--", alpha=0.35)

    ax.set_title(
        "QUANTE OPPORTUNITÀ DI EFFETTUARE O SALVARE BREAK HANNO AVUTO NEGLI SCONTRI DIRETTI DEL 2025?",
        fontsize=14, weight="bold", pad=12
    )

    xmin, xmax = ax.get_xlim()
    dx = (xmax - xmin) * 0.03

    for i in range(len(metrics)):
        if i == 0:
            # BP SALVATI
            x_s = p1_x[i] + dx
            ha_s = "left"
            if x_s > xmax - dx:
                x_s = p1_x[i] - dx
                ha_s = "right"
            
            ax.text(
                x_s, y[i], p1_txt[i],
                fontsize=11, weight="bold",
                va="center", ha=ha_s,
                color=colors[player1],
                zorder=10
                )
            
            x_a = p2_x[i] - dx
            ha_a = "right"
            if x_a < xmin + dx:
                x_a = p2_x[i] + dx
                ha_a = "left"
                
            ax.text(
                x_a, y[i], p2_txt[i],
                fontsize=11, weight="bold",
                va="center", ha=ha_a,
                color=colors[player2],
                zorder=10
                )
            
        else:
            x_s = p1_x[i] - dx
            ha_s = "right"
            if x_s < xmin + dx:
                x_s = p1_x[i] + dx
                ha_s = "left"

            ax.text(
                x_s, y[i], p1_txt[i],
                fontsize=11, weight="bold",
                va="center", ha=ha_s,
                color=colors[player1],
                zorder=10
            )

            x_a = p2_x[i] + dx
            ha_a = "left"
            if x_a > xmax - dx:
                x_a = p2_x[i] - dx
                ha_a = "right"

            ax.text(
                x_a, y[i], p2_txt[i],
                fontsize=11, weight="bold",
                va="center", ha=ha_a,
                color=colors[player2],
                zorder=10
            )

    handles, labels = ax.get_legend_handles_labels()
    by_label = dict(zip(labels, handles))
    ax.legend(by_label.values(), by_label.keys(), frameon=False, fontsize=11, loc="upper left", bbox_to_anchor=(1.02, 1.0))

    plt.tight_layout()
    return fig


def plot_wl_top10_vs_nontop10_area(df, players):
    from matplotlib.lines import Line2D
    
    needed = ["Winner_Rank", "Loser_Rank", "Winner_Name", "Loser_Name"]
    if not all(c in df.columns for c in needed):
        return None

    p1, p2 = players[0], players[1]

    def build_player_matches(dff, p):
        rows = []
        w = dff[dff["Winner_Name"] == p]
        if not w.empty:
            rows.append(pd.DataFrame({
                "player": p,
                "result": "W",
                "opp_rank": pd.to_numeric(w["Loser_Rank"], errors="coerce")
            }))
        l = dff[dff["Loser_Name"] == p]
        if not l.empty:
            rows.append(pd.DataFrame({
                "player": p,
                "result": "L",
                "opp_rank": pd.to_numeric(l["Winner_Rank"], errors="coerce")
            }))
        if not rows:
            return pd.DataFrame(columns=["player", "result", "opp_rank"])
        return pd.concat(rows, ignore_index=True).dropna(subset=["opp_rank"])

    df_players = df[(df["Winner_Name"].isin(players)) | (df["Loser_Name"].isin(players))].copy()
    if df_players.empty:
        return None

    allm = pd.concat([build_player_matches(df_players, p1),
                      build_player_matches(df_players, p2)], ignore_index=True)

    if allm.empty:
        return None

    top10 = allm[allm["opp_rank"] <= 10].copy()
    nontop10 = allm[allm["opp_rank"] > 10].copy()

    def stats_block(dff):
        stats = {}
        for p in players:
            d = dff[dff["player"] == p]
            W = int((d["result"] == "W").sum())
            L = int((d["result"] == "L").sum())
            stats[p] = {"W": W, "L": L, "T": W + L}
        return stats

    def plot_area(ax, stats, title, colors):
        colore_vittorie, colore_totale = colors

        x = np.arange(2)
        wins = np.array([stats[p1]["W"], stats[p2]["W"]], dtype=float)
        total = np.array([stats[p1]["T"], stats[p2]["T"]], dtype=float)

        ax.set_facecolor("#f9f9f9")

        ax.fill_between(x, 0, wins, color=colore_vittorie, alpha=0.45)
        ax.plot(x, wins, color=colore_vittorie, linewidth=2.5, marker="o")

        ax.fill_between(x, wins, total, color=colore_totale, alpha=0.35)
        ax.plot(x, total, color=colore_totale, linewidth=2.5, marker="o")

        ax.set_xticks(x)
        ax.set_xticklabels([get_player_label(p1), get_player_label(p2)],
                           fontsize=12, weight="bold")

        ax.set_ylabel("Numero di match", fontsize=11)
        ax.set_title(title, fontsize=14, weight="bold", pad=10)
        ax.grid(axis="y", linestyle="--", alpha=0.25)

        ymax_val = max(total.max(), 1)
        ax.set_ylim(0, ymax_val * 1.4)
        offset_y = ymax_val * 0.02

        for i, p in enumerate(players):
            W = stats[p]["W"]
            L = stats[p]["L"]
            T = stats[p]["T"]
            winpct = (W / T * 100) if T > 0 else 0.0

            if T > 0:
                ax.text(
                    x[i], total[i] + offset_y,
                    f"W {W} | L {L}\nWin% {winpct:.1f}%",
                    ha="center", va="bottom",
                    fontsize=10, weight="bold", color="black"
                )

        legend_items = [
            Patch(facecolor=colore_vittorie, alpha=0.45, label="Vittorie (area sotto)"),
            Line2D([0], [0], color=colore_vittorie, linewidth=2.5, marker="o", label="Vittorie (linea)"),
            Patch(facecolor=colore_totale, alpha=0.35, label="Sconfitte (area sopra)"),
            Line2D([0], [0], color=colore_totale, linewidth=2.5, marker="o", label="Totale (linea)")
        ]
        ax.legend(handles=legend_items, frameon=False, fontsize=10, loc="upper left")

    stats_top10 = stats_block(top10)
    stats_nontop10 = stats_block(nontop10)

    colors = {players[0].upper(): "#2e6417", players[1].upper(): "#ff914d"}

    fig = Figure(figsize=(13.5, 14), facecolor="#f9f9f9")
    axes = fig.subplots(2, 1)

    plot_area(
        axes[0],
        stats_top10,
        "RENDIMENTO CONTRO TOP 10 DI SINNER E ALCARAZ NEL 2025",
        ("#FF1FDD", "#7A1FFF")
    )

    plot_area(
        axes[1],
        stats_nontop10,
        "RENDIMENTO CONTRO NON TOP 10 DI SINNER E ALCARAZ NEL 2025",
        ("#1E5BFF", "#2ECC71")
    )

    plt.tight_layout(rect=[0, 0, 1, 0.95])
    return fig


def plot_wl_vs_older_younger_ruler(df, players):
    from matplotlib.patches import Polygon, Rectangle
    
    p1, p2 = players[0], players[1]

    possible_w_age = ["Winner_Age", "W_Age", "winner_age"]
    possible_l_age = ["Loser_Age", "L_Age", "loser_age"]

    w_age_col = next((c for c in possible_w_age if c in df.columns), None)
    l_age_col = next((c for c in possible_l_age if c in df.columns), None)

    if w_age_col is None or l_age_col is None:
        return None

    dff = df.copy()
    dff[w_age_col] = pd.to_numeric(dff[w_age_col], errors="coerce")
    dff[l_age_col] = pd.to_numeric(dff[l_age_col], errors="coerce")

    def player_rows(p):
        m = dff[(dff["Winner_Name"] == p) | (dff["Loser_Name"] == p)].copy()

        is_win = (m["Winner_Name"] == p).values
        p_age = np.where(is_win, m[w_age_col].values, m[l_age_col].values)
        o_age = np.where(is_win, m[l_age_col].values, m[w_age_col].values)
        out = m.copy()
        out["__is_win__"] = is_win
        out["__p_age__"] = p_age
        out["__o_age__"] = o_age
        out = out.dropna(subset=["__p_age__", "__o_age__"])
        return out

    def wl_stats(p):
        m = player_rows(p)
        younger = m[m["__o_age__"] < m["__p_age__"]]
        older = m[m["__o_age__"] > m["__p_age__"]]

        def pack(d):
            W = int(d["__is_win__"].sum())
            T = int(len(d))
            L = T - W
            pct = (W / T * 100) if T > 0 else 0.0
            return {"W": W, "L": L, "pct": pct}

        return {"younger": pack(younger), "older": pack(older)}

    stats = {p: wl_stats(p) for p in players}

    player_colors = {p1: "#c1ff72", p2: "#039490"}
    bg = "white"
    track = "#ECECEC"
    tickc = "#BBBBBB"
    textc = "#111111"

    def draw_ruler(ax, y, pct, color, label_left, label_right):
        ax.add_patch(Rectangle((0, y - 0.16), 100, 0.32, facecolor=track, edgecolor="none", zorder=1))
        ax.add_patch(Rectangle((0, y - 0.16), pct, 0.32, facecolor=color, edgecolor="none", alpha=0.88, zorder=2))

        xtri = float(np.clip(pct, 0, 100))
        tri_w, tri_h = 2.6, 0.18
        tri = Polygon(
            [[xtri, y + 0.20], [xtri - tri_w/2, y + 0.20 + tri_h], [xtri + tri_w/2, y + 0.20 + tri_h]],
            closed=True, facecolor=color, edgecolor="none", zorder=3
        )
        ax.add_patch(tri)

        ax.text(-2, y, label_left, ha="right", va="center", fontsize=11, weight="bold", color=textc)
        ax.text(102, y, label_right, ha="left", va="center", fontsize=11, weight="bold", color=textc)
        ax.text(xtri, y - 0.32, f"{pct:.1f}%", ha="center", va="top", fontsize=11, weight="bold", color=color)

    fig = Figure(figsize=(13, 6.2), facecolor=bg)
    axes = fig.subplots(2, 1)

    for ax, p in zip(axes, players):
        ax.set_facecolor(bg)
        ax.set_xlim(-8, 110)
        ax.set_ylim(-0.1, 2.2)

        ax.set_xticks(range(0, 101, 10))
        ax.tick_params(axis="x", labelsize=9, colors="#666666")

        for t in range(0, 101, 10):
            ax.plot([t, t], [0.15, 2.0], color=tickc, linewidth=0.8, alpha=0.25, zorder=0)

        c = player_colors.get(p, "#6A6A6A")
        st_y = stats[p]["younger"]
        st_o = stats[p]["older"]

        draw_ruler(ax, 1.55, st_y["pct"], c, "vs PIÙ GIOVANI", f"W {st_y['W']} | L {st_y['L']}")
        draw_ruler(ax, 0.80, st_o["pct"], c, "vs PIÙ ADULTI", f"W {st_o['W']} | L {st_o['L']}")

        ax.set_title(get_player_label(p), fontsize=14, weight="bold", pad=8, y=0.9)
        ax.set_yticks([])
        for spine in ax.spines.values():
            spine.set_visible(False)

    fig.suptitle(
        "NEL 2025 SINNER E ALCARAZ HANNO VINTO DI PIÙ CONTRO I PIÙ GIOVANI O I PIÙ ADULTI?",
        fontsize=16, weight="bold", y=0.98
    )

    plt.tight_layout(rect=[0, 0, 1, 0.94])
    return fig


def plot_wins_by_seed(df, players):
    
    if "Winner_Seed" not in df.columns:
        return None

    def seed_group(seed):
        if pd.isna(seed) or seed is None:
            return "Non testa di serie"
        try:
            s_val = int(seed)
        except:
            return "Non testa di serie"
            
        if s_val == 1:
            return "Seed 1"
        elif s_val == 2:
            return "Seed 2"
        elif s_val == 3:
            return "Seed 3"
        elif 4 <= s_val <= 8:
            return "Seed 4–8"
        elif 9 <= s_val <= 16:
            return "Seed 9–16"
        else:
            return "Non testa di serie"

    seed_order = [
        "Seed 1",
        "Seed 2",
        "Seed 3",
        "Seed 4–8",
        "Seed 9–16",
        "Non testa di serie"
    ]

    results = {p: {k: 0 for k in seed_order} for p in players}
    
    relevant = df[df["Winner_Name"].isin(players)].copy()
    
    for _, row in relevant.iterrows():
        player = row["Winner_Name"]
        seed = row["Winner_Seed"]
        group = seed_group(seed)
        if group in results[player]:
            results[player][group] += 1

    fig = Figure(figsize=(14, 6), facecolor="white")
    ax = fig.subplots()
    ax.set_facecolor("white")

    x = np.arange(len(seed_order))

    colors = {
        players[0]: "#FF9966",  
        players[1]: "#E30B5C"  
    }

    max_y = 0

    for p in players:
        y = [results[p][k] for k in seed_order]
        curr_max = max(y) if y else 0
        max_y = max(max_y, curr_max)
        
        ax.plot(
            x, y,
            marker="o",
            linewidth=3,
            markersize=8,
            label=get_player_label(p),
            color=colors[p]
        )

        for xi, yi in zip(x, y):
            ax.text(
                xi, yi + 0.15,
                str(yi),
                ha="center",
                va="bottom",
                fontsize=10,
                weight="bold"
            )

    ax.set_xticks(x)
    ax.set_xticklabels(seed_order, fontsize=11, weight="bold")
    ax.set_ylabel("Numero di vittorie", fontsize=12)
    ax.set_title(
        "VITTORIE DI SINNER E ALCARAZ IN BASE ALLA LORO TESTA DI SERIE NEL 2025",
        fontsize=16,
        weight="bold",
        pad=14
    )
    
    ax.set_ylim(0, max(max_y * 1.2, 5))
    ax.grid(axis="y", linestyle="--", alpha=0.3)
    ax.legend(frameon=False, fontsize=12)

    plt.tight_layout()
    return fig


def plot_tourney_summary_two_tables(df, players, top_n_common=14, top_n_exclusive=14):
    from matplotlib.patches import Rectangle
    
    player1, player2 = players[0], players[1]

    required_cols = {"Tourney_Name", "Tourney_Level", "Winner_Name", "Loser_Name"}
    missing = required_cols - set(df.columns)
    if missing:
        return None

    colors = {
        "bg": "#f9f9f9",
        "header": "#EFEFEF",
        "neutral": "#FFFFFF",
        "grid": "#000000",
        "text": "#1f1f1f",
        "sinner": "#0047AB",   
        "alcaraz": "#8B4513"  
    }

    def build_player_tourney_stats(p):
        wins = (
            df[df["Winner_Name"] == p]
            .groupby(["Tourney_Name", "Tourney_Level"])
            .size()
            .rename("Wins")
        )
        losses = (
            df[df["Loser_Name"] == p]
            .groupby(["Tourney_Name", "Tourney_Level"])
            .size()
            .rename("Losses")
        )
        tab = pd.concat([wins, losses], axis=1).fillna(0).reset_index()
        tab["Wins"] = tab["Wins"].astype(int)
        tab["Losses"] = tab["Losses"].astype(int)
        tab["Matches"] = tab["Wins"] + tab["Losses"]
        tab["Win_%"] = np.where(tab["Matches"] > 0, (tab["Wins"] / tab["Matches"]) * 100, 0.0)
        tab["Win_%"] = tab["Win_%"].round(1)
        return tab

    p1 = build_player_tourney_stats(player1).rename(columns={
        "Wins": "P1_Wins", "Losses": "P1_Losses", "Matches": "P1_Matches", "Win_%": "P1_Win_%"
    })
    p2 = build_player_tourney_stats(player2).rename(columns={
        "Wins": "P2_Wins", "Losses": "P2_Losses", "Matches": "P2_Matches", "Win_%": "P2_Win_%"
    })

    merged = pd.merge(
        p1[["Tourney_Name", "Tourney_Level", "P1_Wins", "P1_Losses", "P1_Matches", "P1_Win_%"]],
        p2[["Tourney_Name", "Tourney_Level", "P2_Wins", "P2_Losses", "P2_Matches", "P2_Win_%"]],
        on=["Tourney_Name", "Tourney_Level"],
        how="outer"
    ).fillna(0)

    for c in ["P1_Wins","P1_Losses","P1_Matches","P2_Wins","P2_Losses","P2_Matches"]:
        merged[c] = merged[c].astype(int)
    for c in ["P1_Win_%","P2_Win_%"]:
        merged[c] = merged[c].astype(float).round(1)

    merged["Tot_Matches"] = merged["P1_Matches"] + merged["P2_Matches"]

    both = merged[(merged["P1_Matches"] > 0) & (merged["P2_Matches"] > 0)].copy()
    only_one = merged[((merged["P1_Matches"] > 0) & (merged["P2_Matches"] == 0)) |
                      ((merged["P2_Matches"] > 0) & (merged["P1_Matches"] == 0))].copy()

    both = both.sort_values(["Tot_Matches", "Tourney_Name"], ascending=[False, True]).head(top_n_common)
    only_one = only_one.sort_values(["Tot_Matches", "Tourney_Name"], ascending=[False, True]).head(top_n_exclusive)

    p1lab = get_player_label(player1)
    p2lab = get_player_label(player2)

    def fmt_cell(w, l, m, wp):
        if m <= 0:
            return "—"
        return f"{w}-{l}  ({wp:.1f}%)"

    def prep_display_table(d):
        out = d.copy()
        out["SINNER"] = out.apply(lambda r: fmt_cell(r["P1_Wins"], r["P1_Losses"], r["P1_Matches"], r["P1_Win_%"]), axis=1)
        out["ALCARAZ"] = out.apply(lambda r: fmt_cell(r["P2_Wins"], r["P2_Losses"], r["P2_Matches"], r["P2_Win_%"]), axis=1)
        out = out[["Tourney_Name", "Tourney_Level", "SINNER", "ALCARAZ"]]
        out = out.rename(columns={"Tourney_Name": "TORNEO", "Tourney_Level": "LIVELLO"})
        return out

    both_disp = prep_display_table(both)
    one_disp = prep_display_table(only_one)

    def draw_table(ax, title, data_table, left, bottom, width, height):
        col_labels = list(data_table.columns)
        n_rows = len(data_table) + 1  
        
        col_fracs = np.array([0.46, 0.10, 0.22, 0.22])
        col_fracs = col_fracs / col_fracs.sum()
        col_w = col_fracs * width
        row_h = height / n_rows if n_rows > 0 else 0

        ax.text(left, bottom + height + row_h*0.35, title,
                ha="left", va="bottom", fontsize=13, weight="bold", color=colors["text"])

        y_top = bottom + height

        x = left
        for j, lab in enumerate(col_labels):
            ax.add_patch(Rectangle((x, y_top - row_h), col_w[j], row_h,
                                   facecolor=colors["header"], edgecolor=colors["grid"], linewidth=1.0))
            ax.text(x + col_w[j]/2, y_top - row_h/2, lab,
                    ha="center", va="center", fontsize=10.5, weight="bold", color=colors["text"])
            x += col_w[j]
        
        if len(data_table) == 0:
            ax.text(left + width/2, bottom + height/2, "Nessun dato disponibile.", ha="center", va="center")
            return

        for i in range(len(data_table)):
            y0 = y_top - (i + 2) * row_h
            x = left
            for j, col in enumerate(col_labels):
                ax.add_patch(Rectangle((x, y0), col_w[j], row_h,
                                       facecolor=colors["neutral"], edgecolor=colors["grid"], linewidth=1.0))

                val = str(data_table.iloc[i, j])

                txt_color = colors["text"]
                weight = "normal"
                if col == "SINNER":
                    txt_color = colors["sinner"]
                    weight = "bold"
                elif col == "ALCARAZ":
                    txt_color = colors["alcaraz"]
                    weight = "bold"

                if col == "TORNEO":
                    ax.text(x + 0.01*width, y0 + row_h/2, val,
                            ha="left", va="center", fontsize=10, color=txt_color, weight=weight)
                else:
                    ax.text(x + col_w[j]/2, y0 + row_h/2, val,
                            ha="center", va="center", fontsize=10, color=txt_color, weight=weight)

                x += col_w[j]

    fig = Figure(figsize=(16, 9), facecolor=colors["bg"])
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_axis_off()

    fig.suptitle(
        f"PRESTAZIONI NEI VARI TORNEI DEL 2025",
        fontsize=16, weight="bold", y=0.97
    )

    left = 0.04
    width = 0.92

    top_table_bottom = 0.50
    top_table_height = 0.34

    bottom_table_bottom = 0.08
    bottom_table_height = 0.34

    draw_table(
        ax,
        title="TORNEI DOVE HANNO PARTECIPATO ENTRAMBI",
        data_table=both_disp,
        left=left, bottom=top_table_bottom, width=width, height=top_table_height
    )

    draw_table(
        ax,
        title="TORNEI DOVE HA PARTECIPATO SOLO UNO DEI DUE",
        data_table=one_disp,
        left=left, bottom=bottom_table_bottom, width=width, height=bottom_table_height
    )

    ax.text(0.5, 0.02,
            f"Celle: W-L (Win%)",
            ha="center", va="center", fontsize=11, color=colors["text"], transform=ax.transAxes)

    return fig


def plot_second_serve_efficiency_boxplot_by_surface_colors(df, player1, player2):
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    
    players = [player1, player2]
    SURFACES = ["Hard", "Clay", "Grass"]
    SURFACE_NAMES = {"Hard": "Cemento", "Clay": "Terra", "Grass": "Erba"}

    required = [
        "Winner_Name", "Loser_Name", "Surface",
        "W_ServicePoints", "W_1stIn", "W_2ndWon",
        "L_ServicePoints", "L_1stIn", "L_2ndWon"
    ]
    missing = [c for c in required if c not in df.columns]
    if missing:
        return None

    rows = []
    for _, row in df.iterrows():
        s = row["Surface"]
        if s not in SURFACES:
            continue

        for p in players:
            if row["Winner_Name"] == p:
                svpt = row["W_ServicePoints"]
                first_in = row["W_1stIn"]
                second_won = row["W_2ndWon"]
            elif row["Loser_Name"] == p:
                svpt = row["L_ServicePoints"]
                first_in = row["L_1stIn"]
                second_won = row["L_2ndWon"]
            else:
                continue

            if pd.isna(svpt) or pd.isna(first_in) or pd.isna(second_won):
                continue

            try:
                svpt = float(svpt)
                first_in = float(first_in)
                second_won = float(second_won)
            except:
                continue

            second_in = svpt - first_in
            if second_in <= 0:
                continue

            pct = (second_won / second_in) * 100.0
            rows.append({"player": p, "surface": s, "second_pct": pct})

    data = pd.DataFrame(rows)
    if data.empty:
        return None

    surface_pair_colors = {
        "Hard":  ("#4169E1", "#90CAF9"), 
        "Clay":  ("#CD7F32", "#FBCEB1"), 
        "Grass": ("#2E7D32", "#A5D6A7")  
    }

    fig = Figure(figsize=(14, 7), facecolor="white")
    ax = fig.subplots()
    ax.set_facecolor("white")

    base_pos = np.arange(len(SURFACES))
    offset = 0.22

    values = []
    positions = []
    facecolors = []

    for i, s in enumerate(SURFACES):
        v1 = data[(data["player"] == player1) & (data["surface"] == s)]["second_pct"].values
        v2 = data[(data["player"] == player2) & (data["surface"] == s)]["second_pct"].values

        c1, c2 = surface_pair_colors[s]

        if len(v1) > 0:
            values.append(v1)
            positions.append(base_pos[i] - offset)
            facecolors.append(c1)

        if len(v2) > 0:
            values.append(v2)
            positions.append(base_pos[i] + offset)
            facecolors.append(c2)

    if not values:
        return None

    bp = ax.boxplot(
        values,
        positions=positions,
        widths=0.34,
        patch_artist=True,
        showfliers=True,
        flierprops=dict(
            marker="o",
            markerfacecolor="black",
            markeredgecolor="black",
            markersize=4,
            alpha=0.9
        ),
        boxprops=dict(linewidth=1.6, color="black"),
        whiskerprops=dict(color="black", linewidth=1.3),
        capprops=dict(color="black", linewidth=1.3),
        medianprops=dict(color="black", linewidth=1.6)
    )

    for patch, fc in zip(bp["boxes"], facecolors):
        patch.set_facecolor(fc)
        patch.set_alpha(0.85)
        patch.set_edgecolor("black")
        patch.set_linewidth(1.6)

    ax.set_xticks(base_pos)
    ax.set_xticklabels([SURFACE_NAMES[s] for s in SURFACES], fontsize=12, weight="bold", color="black")
    ax.set_ylabel("% punti vinti con la seconda", fontsize=12, color="black")
    ax.tick_params(axis="y", colors="black")

    y = data["second_pct"].values
    if len(y) > 0:
        y_low = max(0, np.percentile(y, 2) - 5)
        y_high = min(100, np.percentile(y, 98) + 5)
        ax.set_ylim(y_low, y_high)

    tick_start = np.floor(ax.get_ylim()[0] / 5) * 5
    tick_end = np.ceil(ax.get_ylim()[1] / 5) * 5
    ax.set_yticks(np.arange(tick_start, tick_end + 0.1, 5))

    ax.set_title(
        "EFFICIENZA DELLA SECONDA DI SERVIZIO PER SUPERFICIE NEL 2025",
        fontsize=15, weight="bold", color="black", pad=14
    )

    ax.grid(axis="y", linestyle="--", alpha=0.25, color="black")

    legend_handles = [
        
        Line2D([0], [0], marker="s", linestyle="None",
                   markerfacecolor="#4169E1", markeredgecolor="black",
                   markersize=12, label="SINNER – Cemento"),
        Line2D([0], [0], marker="s", linestyle="None",
                   markerfacecolor="#CD7F32", markeredgecolor="black",
                   markersize=12, label="SINNER – Terra"),
        Line2D([0], [0], marker="s", linestyle="None",
                   markerfacecolor="#2E7D32", markeredgecolor="black",
                   markersize=12, label="SINNER – Erba"),

        Line2D([0], [0], marker="s", linestyle="None",
                   markerfacecolor="#90CAF9", markeredgecolor="black",
                   markersize=12, label="ALCARAZ – Cemento"),
        Line2D([0], [0], marker="s", linestyle="None",
                   markerfacecolor="#FBCEB1", markeredgecolor="black",
                   markersize=12, label="ALCARAZ – Terra"),
        Line2D([0], [0], marker="s", linestyle="None",
                   markerfacecolor="#A5D6A7", markeredgecolor="black",
                   markersize=12, label="ALCARAZ – Erba"),
        ]
    
    ax.legend(
        handles=legend_handles,
        frameon=False,
        fontsize=10,
        loc="upper left",
        ncol=2
        )

    plt.tight_layout()
    return fig


def plot_second_serve_efficiency_h2h_scatter(df, player1, player2):
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    
    SURFACES = ["Hard", "Clay", "Grass"]
    SURFACE_NAMES = {"Hard": "CEMENTO", "Clay": "TERRA", "Grass": "ERBA"}

    surface_colors = {
        "Hard":  {"Sinner": "#0052cc", "Alcaraz": "#4b0082"},   
        "Clay":  {"Sinner": "#00bfff", "Alcaraz": "#dda0dd"},   
        "Grass": {"Sinner": "#7fffd4", "Alcaraz": "#ff69b4"}    
    }

    markers = {"Sinner": "o", "Alcaraz": "^"}

    name_to_role = {
        "Jannik Sinner": "Sinner",
        "Carlos Alcaraz": "Alcaraz"
    }

    def role_for(player_name: str) -> str:
        if player_name in name_to_role:
            return name_to_role[player_name]
        return "Sinner" if player_name == player1 else "Alcaraz"

    h2h = df[
        ((df["Winner_Name"] == player1) & (df["Loser_Name"] == player2)) |
        ((df["Winner_Name"] == player2) & (df["Loser_Name"] == player1))
    ].copy()

    rows = []
    
    if "Tourney_Date" in h2h.columns:
        h2h = h2h.sort_values("Tourney_Date")

    if not h2h.empty:
        for match_idx, row in h2h.reset_index(drop=True).iterrows():
            s = row.get("Surface", None)
            if s not in SURFACES:
                continue

            for p in (player1, player2):
                if row["Winner_Name"] == p:
                    svpt = row.get("W_ServicePoints")
                    first_in = row.get("W_1stIn")
                    second_won = row.get("W_2ndWon")
                else:
                    svpt = row.get("L_ServicePoints")
                    first_in = row.get("L_1stIn")
                    second_won = row.get("L_2ndWon")

                if pd.isna(svpt) or pd.isna(first_in) or pd.isna(second_won):
                    continue

                try:
                    svpt = float(svpt)
                    first_in = float(first_in)
                    second_won = float(second_won)
                except:
                    continue

                second_in = svpt - first_in
                if second_in <= 0:
                    continue

                pct = (second_won / second_in) * 100

                rows.append({
                    "match_idx": match_idx + 1,  
                    "player": p,
                    "role": role_for(p),      
                    "surface": s,
                    "pct": pct
                })

    if rows:
        data = pd.DataFrame(rows)
    else:
        data = pd.DataFrame(columns=["match_idx", "player", "role", "surface", "pct"])

    fig = Figure(figsize=(15, 6), facecolor="white")
    ax = fig.subplots()
    ax.set_facecolor("white")
    if len(data) > 0:
        x_all = np.sort(data["match_idx"].unique())
        ax.set_xticks(x_all)
        ax.set_xticklabels(x_all, fontsize=10)
        
        y_min = data["pct"].min()
        y_max = data["pct"].max()
        if y_max - y_min < 10:
             y_max += 5
             y_min -= 5
        ax.set_ylim(y_min - 5, min(100, y_max + 8)) 
    else:
        ax.set_xticks([])
        ax.set_ylim(0, 100)
    for s in SURFACES:
        for role in ("Sinner", "Alcaraz"):
            d = data[(data["surface"] == s) & (data["role"] == role)]
            if d.empty:
                continue

            c = surface_colors.get(s, {}).get(role, "gray")
            m = markers.get(role, "o")

            ax.scatter(
                d["match_idx"],
                d["pct"],
                color=c,
                marker=m,
                s=110,
                edgecolor="black",
                linewidth=1.2,
                zorder=3,
                label=f"{role.upper()} – {SURFACE_NAMES.get(s, s)}"
            )

    ax.set_xlabel("Match", fontsize=11)
    ax.set_ylabel("% punti vinti con la seconda", fontsize=11)
    ax.set_title(
        f"EFFICIENZA DELLA SECONDA DI SERVIZIO NEGLI SCONTRI DIRETTI DEL 2025",
        fontsize=14, weight="bold", pad=15
    )

    ax.grid(axis="y", linestyle="--", alpha=0.35, color="#d3d3d3")
    
    legend_elements = []
    
    for s in ["Hard", "Clay", "Grass"]:
         c = surface_colors[s]["Sinner"]
         legend_elements.append(
             Line2D([0], [0], marker="o", color=c, label=f"SINNER – {SURFACE_NAMES[s]}",
                    markerfacecolor=c, markeredgecolor='k', markersize=9, linestyle="None")
         )
         
    for s in ["Hard", "Clay", "Grass"]:
         c = surface_colors[s]["Alcaraz"]
         legend_elements.append(
             Line2D([0], [0], marker="^", color=c, label=f"ALCARAZ – {SURFACE_NAMES[s]}",
                    markerfacecolor=c, markeredgecolor='k', markersize=9, linestyle="None")
         )

    ax.legend(
        handles=legend_elements,
        loc="lower left",
        bbox_to_anchor=(0.0, 0.01),
        ncol=3,
        frameon=False,
        fontsize=9,
        columnspacing=1.0
    )

    plt.tight_layout()
    return fig



def plot_resistenza_divergente(df, players):
    from matplotlib.ticker import FuncFormatter
    
    player1, player2 = players[0], players[1]
    minutes_col = "Minutes"
    bestof_col = "Best_of"
    
    needed = {"Winner_Name", "Loser_Name", minutes_col, bestof_col}
    missing = needed - set(df.columns)
    if missing:
        return None

    bins = [0, 60, 120, 180, 240, 300, 360]
    bin_labels = ["< 1h", "1–2h", "2–3h", "3–4h", "4–5h", "5–6h"]

    base = df[
        (df["Winner_Name"].isin([player1, player2])) |
        (df["Loser_Name"].isin([player1, player2]))
    ].copy()

    base[minutes_col] = pd.to_numeric(base[minutes_col], errors="coerce")
    base = base[base[minutes_col].notna() & (base[minutes_col] > 0)].copy()

    base[bestof_col] = pd.to_numeric(base[bestof_col], errors="coerce")
    base = base[base[bestof_col].isin([3, 5])].copy()

    if base.empty:
        return None

    base["Duration_Bin"] = pd.cut(base[minutes_col], bins=bins, labels=bin_labels, right=False)
    base = base[base["Duration_Bin"].notna()].copy()

    if base.empty:
        return None

    rows = []
    for _, r in base.iterrows():
        if r["Winner_Name"] in (player1, player2):
            rows.append({
                "Player": r["Winner_Name"],
                "Result": "Win",
                "BestOf": int(r[bestof_col]),
                "Duration_Bin": r["Duration_Bin"]
            })
        if r["Loser_Name"] in (player1, player2):
            rows.append({
                "Player": r["Loser_Name"],
                "Result": "Loss",
                "BestOf": int(r[bestof_col]),
                "Duration_Bin": r["Duration_Bin"]
            })

    long = pd.DataFrame(rows)
    if long.empty:
        return None

    pivot = (
        long.groupby(["BestOf", "Duration_Bin", "Player", "Result"])
            .size()
            .unstack(["Player", "Result"], fill_value=0)
    )

    for p in (player1, player2):
        for res in ("Win", "Loss"):
            if (p, res) not in pivot.columns:
                pivot[(p, res)] = 0

    pivot = pivot.reindex(
        pd.MultiIndex.from_product([[3, 5], bin_labels], names=["BestOf", "Duration_Bin"]),
        fill_value=0
    )

    SIN_WIN = "#003399"
    SIN_LOS = "#7FFFD4"
    ALC_WIN = "#991199"
    ALC_LOS = "#DF73FF"

    abs_formatter = FuncFormatter(lambda x, pos: f"{int(abs(x))}")

    abs_formatter = FuncFormatter(lambda x, pos: f"{int(abs(x))}") # 3.0 -> "3"

    fig = Figure(figsize=(22, 11), facecolor="white")
    axes = fig.subplots(2, 1, sharex=False)

    def draw_bestof(ax, bo):
        d = pivot.loc[(bo,)]
        y = np.arange(len(bin_labels))

        sw = d[(player1, "Win")].values.astype(int)
        sl = d[(player1, "Loss")].values.astype(int)
        aw = d[(player2, "Win")].values.astype(int)
        al = d[(player2, "Loss")].values.astype(int)

        ax.barh(y, -sw, color=SIN_WIN, edgecolor="black", linewidth=0.8, label=f"{get_player_label(player1)} WIN")
        ax.barh(y, -sl, left=-sw, color=SIN_LOS, edgecolor="black", linewidth=0.8, label=f"{get_player_label(player1)} LOSS")

        ax.barh(y,  aw, color=ALC_WIN, edgecolor="black", linewidth=0.8, label=f"{get_player_label(player2)} WIN")
        ax.barh(y,  al, left=aw, color=ALC_LOS, edgecolor="black", linewidth=0.8, label=f"{get_player_label(player2)} LOSS")

        ax.axvline(0, color="black", linewidth=1.0)
        ax.set_yticks(y)
        ax.set_yticklabels(bin_labels, fontsize=11)
        ax.grid(axis="x", linestyle="--", alpha=0.25)
        ax.set_title(f"BEST OF {bo}", fontsize=14, weight="bold", pad=10)

        max_val = max(sw.max() + sl.max(), aw.max() + al.max(), 5) # minimum 5
        limit = max_val * 1.15
        ax.set_xlim(-limit, limit)
        ax.margins(x=0.0)
        ax.xaxis.set_major_formatter(abs_formatter)


        for i in range(len(bin_labels)):

            tot_s = sw[i] + sl[i]
            if tot_s > 0:
                if sw[i] > 0:
                    ax.text(
                        -(sw[i] / 2), i,
                        f"{100*sw[i]/tot_s:.0f}%",
                        ha="center", va="center",
                        fontsize=7, color="white" if sw[i] > 2 else "black", alpha=0.9
                    )
                if sl[i] > 0:
                    ax.text(
                        -(sw[i] + sl[i]/2), i,
                        f"{100*sl[i]/tot_s:.0f}%",
                        ha="center", va="center",
                        fontsize=7, color="black", alpha=0.9
                    )
                
                ax.text(
                    -(tot_s + 0.5), i,
                    f"{sw[i]}/{tot_s}",
                    ha="right", va="center",
                    fontsize=8, color="black", weight="bold"
                )

            tot_a = aw[i] + al[i]
            if tot_a > 0:
                if aw[i] > 0:
                    ax.text(
                        (aw[i] / 2), i,
                        f"{100*aw[i]/tot_a:.0f}%",
                        ha="center", va="center",
                        fontsize=7, color="white" if aw[i] > 2 else "black", alpha=0.9
                    )
                if al[i] > 0:
                    ax.text(
                        (aw[i] + al[i]/2), i,
                        f"{100*al[i]/tot_a:.0f}%",
                        ha="center", va="center",
                        fontsize=7, color="black", alpha=0.9
                    )

                ax.text(
                    (tot_a + 0.5), i,
                    f"{aw[i]}/{tot_a}",
                    ha="left", va="center",
                    fontsize=8, color="black", weight="bold"
                )

    draw_bestof(axes[0], 3)
    draw_bestof(axes[1], 5)

    axes[0].tick_params(axis="x", labelbottom=True)

    fig.suptitle(
        "CHI DEI DUE HA MOSTRATO MAGGIORE RESISTENZA NEL 2025?",
        fontsize=16, weight="bold", y=0.98
    )

    axes[0].set_xlabel("Numero match", fontsize=12)
    axes[1].set_xlabel("Numero match", fontsize=12)

    handles, labels_ = axes[0].get_legend_handles_labels()
    seen = set()
    h2, l2 = [], []
    for h, lab in zip(handles, labels_):
        if lab not in seen:
            h2.append(h); l2.append(lab); seen.add(lab)

    fig.legend(h2, l2, loc="lower center", ncol=4, frameon=False, fontsize=11, bbox_to_anchor=(0.5, 0.02))

    fig.tight_layout(rect=[0, 0.07, 1, 0.97], h_pad=3.5)
    return fig


def plot_winrate_vs_hand_heatmap(df, players):
    player1, player2 = players[0], players[1]
    
    needed = {"Winner_Name", "Loser_Name", "Winner_Hand", "Loser_Hand"}
    missing = needed - set(df.columns)
    if missing:
        return None

    def norm_hand(x):
        if pd.isna(x):
            return np.nan
        s = str(x).strip().lower()
        if s in ("l", "left", "mancino", "left-handed"):
            return "Mancino"
        if s in ("r", "right", "destro", "right-handed"):
            return "Destro"
        return np.nan

    rows = []

    sub = df[
        (df["Winner_Name"].isin([player1, player2])) |
        (df["Loser_Name"].isin([player1, player2]))
    ].copy()

    if sub.empty:
        return None

    for _, r in sub.iterrows():
        if r["Winner_Name"] == player1:
            opp_hand = norm_hand(r.get("Loser_Hand"))
            rows.append({"Player": player1, "Opp_Hand": opp_hand, "Result": "Win"})
        elif r["Winner_Name"] == player2:
            opp_hand = norm_hand(r.get("Loser_Hand"))
            rows.append({"Player": player2, "Opp_Hand": opp_hand, "Result": "Win"})

        if r["Loser_Name"] == player1:
            opp_hand = norm_hand(r.get("Winner_Hand"))
            rows.append({"Player": player1, "Opp_Hand": opp_hand, "Result": "Loss"})
        elif r["Loser_Name"] == player2:
            opp_hand = norm_hand(r.get("Winner_Hand"))
            rows.append({"Player": player2, "Opp_Hand": opp_hand, "Result": "Loss"})

    long = pd.DataFrame(rows).dropna(subset=["Opp_Hand"])

    if long.empty:
        return None

    agg = (
        long.groupby(["Player", "Opp_Hand", "Result"])
            .size()
            .unstack(fill_value=0)
            .reset_index()
    )

    if "Win" not in agg.columns:
        agg["Win"] = 0
    if "Loss" not in agg.columns:
        agg["Loss"] = 0

    agg["Win_%"] = (agg["Win"] / (agg["Win"] + agg["Loss"]) * 100).round(1)

    heat = agg.pivot(index="Player", columns="Opp_Hand", values="Win_%").reindex([player1, player2])

    for col in ["Destro", "Mancino"]:
        if col not in heat.columns:
            heat[col] = np.nan
    heat = heat[["Destro", "Mancino"]]



    fig = Figure(figsize=(7, 3.8), facecolor="white")
    ax = fig.subplots()
    ax.set_facecolor("white")
    if heat.isna().all().all():
        im = ax.imshow([[0,0],[0,0]], aspect="auto", vmin=0, vmax=100, cmap="viridis")
    else:
        im = ax.imshow(heat.values, aspect="auto", vmin=0, vmax=100)

    ax.set_xticks([0, 1])
    ax.set_xticklabels(["DESTRI", "MANCINI"], fontsize=11, weight="bold")
    ax.set_yticks([0, 1])
    ax.set_yticklabels([get_player_label(player1), get_player_label(player2)], fontsize=11, weight="bold")

    for i in range(len([player1, player2])):
        for j in range(2):
            if i < len(heat) and j < len(heat.columns):
                val = heat.iloc[i, j]
                txt = "—" if pd.isna(val) else f"{val:.1f}%"
                ax.text(j, i, txt, ha="center", va="center", fontsize=12, weight="bold", color="black" if pd.isna(val) or val > 50 else "white")

    ax.set_title("NEL 2025 HANNO VINTO DI PIÙ CONTRO DESTRI O MANCINI?", fontsize=14, weight="bold", pad=12)

    ax.set_xticks(np.arange(-.5, 2, 1), minor=True)
    ax.set_yticks(np.arange(-.5, 2, 1), minor=True)
    ax.grid(which="minor", color="black", linestyle="-", linewidth=1)
    ax.tick_params(which="minor", bottom=False, left=False)

    cbar = fig.colorbar(im, ax=ax, fraction=0.05, pad=0.04)
    cbar.set_label("Win %", rotation=90)

    plt.tight_layout()
    return fig


def plot_service_winpct_strip(df, players):
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch
    
    player1, player2 = players[0], players[1]
    
    player1 = str(player1).strip()
    player2 = str(player2).strip()

    required = {
        "Winner_Name", "Loser_Name",
        "Winner_Ht", "Loser_Ht",
        "W_1stWon", "W_2ndWon", "W_ServicePoints",
        "L_1stWon", "L_2ndWon", "L_ServicePoints"
    }
    missing = required - set(df.columns)
    if missing:
        return None

    sub = df[
        (df["Winner_Name"].isin([player1, player2])) |
        (df["Loser_Name"].isin([player1, player2]))
    ].copy()

    if sub.empty:
        return None

    rows = []

    for _, r in sub.iterrows():
        if str(r["Winner_Name"]).strip() in (player1, player2):
            svpt = r["W_ServicePoints"]
            if pd.notna(svpt) and svpt > 0:
                pct = (r["W_1stWon"] + r["W_2ndWon"]) / svpt * 100
                rows.append({
                    "Player": str(r["Winner_Name"]).strip(),
                    "ServeWinPct": pct,
                    "Ht": r.get("Winner_Ht")
                })

        if str(r["Loser_Name"]).strip() in (player1, player2):
            svpt = r["L_ServicePoints"]
            if pd.notna(svpt) and svpt > 0:
                pct = (r["L_1stWon"] + r["L_2ndWon"]) / svpt * 100
                rows.append({
                    "Player": str(r["Loser_Name"]).strip(),
                    "ServeWinPct": pct,
                    "Ht": r.get("Loser_Ht")
                })

    data = pd.DataFrame(rows).dropna(subset=["ServeWinPct"])
    data = data[data["ServeWinPct"].between(0, 100)].copy()

    if data.empty:
        return None

    h1_val = pd.to_numeric(data[data["Player"] == player1]["Ht"], errors="coerce").median()
    h1 = int(round(h1_val)) if pd.notna(h1_val) else "?"

    h2_val = pd.to_numeric(data[data["Player"] == player2]["Ht"], errors="coerce").median()
    h2 = int(round(h2_val)) if pd.notna(h2_val) else "?"

    color_sinner = "#2E7D32"   
    color_alcaraz = "#D81B60"  

    fig = Figure(figsize=(14, 5.5), facecolor="white")
    ax = fig.subplots()
    ax.set_facecolor("white")

    np.random.seed(7)
    jitter = 0.05

    d1 = data[data["Player"] == player1]
    if not d1.empty:
        y1 = 1.0 + np.random.uniform(-jitter, jitter, size=len(d1))
        ax.scatter(
            d1["ServeWinPct"], y1,
            s=38, alpha=0.55,
            color=color_sinner,
            edgecolor="black", linewidth=0.5
        )
        ax.axvline(
            np.median(d1["ServeWinPct"]),
            color=color_sinner,
            linestyle="--",
            linewidth=2
        )

    d2 = data[data["Player"] == player2]
    if not d2.empty:
        y2 = 0.0 + np.random.uniform(-jitter, jitter, size=len(d2))
        ax.scatter(
            d2["ServeWinPct"], y2,
            s=38, alpha=0.55,
            color=color_alcaraz,
            edgecolor="black", linewidth=0.5
        )
        ax.axvline(
            np.median(d2["ServeWinPct"]),
            color=color_alcaraz,
            linestyle="--",
            linewidth=2
        )

    ax.set_yticks([1.0, 0.0])
    ax.set_yticklabels(
        [get_player_label(player1), get_player_label(player2)],
        fontsize=12,
        weight="bold"
    )
    ax.set_ylim(-0.35, 1.35)

    ax.set_xlim(40, 95)
    ax.grid(axis="x", linestyle="--", alpha=0.25)

    ax.set_xlabel("% PUNTI VINTI AL SERVIZIO (match-by-match)", fontsize=12)
    ax.set_title(
        "QUANTO HA INFLUITO L'ALTEZZA AI TURNI DI SERVIZIO DEL 2025?",
        fontsize=16,
        weight="bold",
        pad=12
    )

    legend_elements = [
        Patch(facecolor=color_sinner, edgecolor="black",
              label=f"{get_player_label(player1)} ({h1} cm)"),
        Patch(facecolor=color_alcaraz, edgecolor="black",
              label=f"{get_player_label(player2)} ({h2} cm)")
    ]

    ax.legend(
        handles=legend_elements,
        frameon=True,
        facecolor="white",
        edgecolor="black",
        fontsize=11,
        loc="center left",
        bbox_to_anchor=(1.02, 0.5)
    )

    plt.tight_layout(rect=[0, 0, 0.85, 1])
    return fig


def plot_rank_points_evolution(df, players):
    import matplotlib.dates as mdates
    from matplotlib.lines import Line2D
    
    player1, player2 = players[0], players[1]
    
    if "Tourney_Date" not in df.columns or "Winner_Rank_Points" not in df.columns:
        return None

    def extract_ranking_history(p):
        w = df[df["Winner_Name"] == p][["Tourney_Date", "Winner_Rank_Points"]].rename(
            columns={"Winner_Rank_Points": "Points"}
        )
        l = df[df["Loser_Name"] == p][["Tourney_Date", "Loser_Rank_Points"]].rename(
            columns={"Loser_Rank_Points": "Points"}
        )
        hist = pd.concat([w, l], ignore_index=True)
        hist["Tourney_Date"] = pd.to_datetime(hist["Tourney_Date"], errors="coerce")
        hist = hist.dropna(subset=["Tourney_Date"])
        hist["Points"] = pd.to_numeric(hist["Points"], errors="coerce")
        
        hist.sort_values("Tourney_Date", inplace=True)
        hist.drop_duplicates(subset="Tourney_Date", keep="last", inplace=True)
        return hist.set_index("Tourney_Date")

    h1 = extract_ranking_history(player1)
    h2 = extract_ranking_history(player2)
    
    if h1.empty or h2.empty:
        return None

    combined = h1.join(h2, lsuffix="_p1", rsuffix="_p2", how="outer")
    combined.sort_index(inplace=True)
    
    combined.ffill(inplace=True)
    combined.dropna(inplace=True)

    if combined.empty:
        return None

    combined.dropna(inplace=True)

    if combined.empty:
        return None
    fig = Figure(figsize=(12, 6), facecolor="#f9f9f9")
    ax = fig.subplots()
    ax.set_facecolor("#f9f9f9")
    
    c1 = "#E52B50"  
    c2 = "#FF00FF"  
    
    ax.plot(combined.index, combined["Points_p1"], label=get_player_label(player1), color=c1, linewidth=3)
    ax.plot(combined.index, combined["Points_p2"], label=get_player_label(player2), color=c2, linewidth=3)
    
    diff = combined["Points_p1"] - combined["Points_p2"]
    sign = np.sign(diff)
    
    sign_prev = sign.shift(1)
    
    crossovers = (sign != sign_prev) & (sign_prev.notna()) & (sign != 0) & (sign_prev != 0) & (diff != 0)
    
    crossover_dates = crossovers[crossovers].index
    
    for date in crossover_dates:
        p1_val = combined.loc[date, "Points_p1"]
        p2_val = combined.loc[date, "Points_p2"]
        y_cross = (p1_val + p2_val) / 2
        
        ax.scatter([date], [y_cross], color="#FFD700", s=150, zorder=5, edgecolor="black", linewidth=1.5, marker="*")

    ax.set_title("EVOLUZIONE DEI PUNTI RANKING 2025 DI SINNER E ALCARAZ", fontsize=15, weight="bold", pad=20)
    ax.set_ylabel("Punti Ranking", fontsize=12)
    ax.grid(axis="y", linestyle="--", alpha=0.35)
    
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
    ax.set_xlabel("Mesi", fontsize=11)

    legend_handles = [
        Line2D([0], [0], color=c1, lw=3, label=get_player_label(player1)),
        Line2D([0], [0], color=c2, lw=3, label=get_player_label(player2)),
        Line2D([0], [0], color="white", marker="*", markerfacecolor="#FFD700", markeredgecolor="black", markersize=10, label="SORPASSO")
    ]
    ax.legend(handles=legend_handles, frameon=False, fontsize=12, loc="best")
    
    plt.tight_layout()
    return fig



def plot_vertical_players_3bars_stacked(df, players):

    W = {p: [] for p in players}
    L = {p: [] for p in players}

    for s in SURFACES:
        df_s = df[df["Surface"] == s]
        for p in players:
            w = (df_s["Winner_Name"] == p).sum()
            l = (df_s["Loser_Name"] == p).sum()
            W[p].append(w)
            L[p].append(l)

    total_wins = sum(sum(W[p]) for p in players)
    total_losses = sum(sum(L[p]) for p in players)
    
    if total_wins + total_losses == 0:
        return None

    x_group = np.arange(len(players))
    width = 0.22
    offsets = {"Hard": -width, "Grass": 0.0, "Clay": width}

    fig = Figure(figsize=(14, 7), facecolor="#f9f9f9")
    ax = fig.subplots()
    
    legend_handles = []
    
    for si, s in enumerate(SURFACES):
        x = x_group + offsets[s]
        wins_vals = [W[p][si] for p in players]
        
        rects_w = ax.bar(x, wins_vals, width, label=f"Vittorie {SURFACE_NAMES.get(s, s).lower()}", 
                       color=SURFACE_COLORS[s], edgecolor="black", linewidth=1.0)
        
        if si == 0:
             pass

    for si, s in enumerate(SURFACES):
        x = x_group + offsets[s]
        wins_vals = [W[p][si] for p in players]
        loss_vals = [L[p][si] for p in players]
        
        rects_l = ax.bar(x, loss_vals, width, bottom=wins_vals, 
                       color="#999999", edgecolor="black", linewidth=1.0, label="Sconfitte" if si==0 else "")

        for i_p, p in enumerate(players):
            w_cnt = wins_vals[i_p]
            l_cnt = loss_vals[i_p]
            total = w_cnt + l_cnt
            
            if total > 0:
                pct_w = (w_cnt / total) * 100
                pct_l = (l_cnt / total) * 100
                
                label_text = f"V {pct_w:.1f}% | S {pct_l:.1f}%"
                
                ax.text(x[i_p], total + 0.5, label_text, 
                        ha='center', va='bottom', fontsize=8, weight="bold", color="#222")

    ax.set_title(
        "SU QUALE SUPERFICIE HANNO VINTO DI PIÙ NEL 2025 ALCARAZ E SINNER?",
        fontsize=15,
        weight="bold",
        pad=20
    )
    ax.set_ylabel("Numero di partite", fontsize=11)
    ax.set_xticks(x_group)
    ax.set_xticklabels([get_player_label(p) for p in players], fontsize=13, weight="bold")
    ax.grid(axis="y", linestyle="--", alpha=0.35)

    max_height = 0
    for p_idx in range(len(players)):
        for si in range(len(SURFACES)):
             h = W[players[p_idx]][si] + L[players[p_idx]][si]
             if h > max_height: max_height = h
    ax.set_ylim(0, max_height * 1.25)

    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor=SURFACE_COLORS["Hard"], edgecolor='black', label='Vittorie cemento'),
        Patch(facecolor=SURFACE_COLORS["Clay"], edgecolor='black', label='Vittorie terra'),
        Patch(facecolor=SURFACE_COLORS["Grass"], edgecolor='black', label='Vittorie erba'),
        Patch(facecolor="#999999", edgecolor='black', label='Sconfitte')
    ]
    ax.legend(handles=legend_elements, frameon=False, fontsize=10, ncol=2, loc='upper right')
    
    plt.tight_layout()
    return fig

def plot_tiebreak_3d_blocks(df, player1, player2):
    players = [player1, player2]
    
    sub = df[
        (df["Winner_Name"].isin(players)) |
        (df["Loser_Name"].isin(players))
    ].copy()
    
    if sub.empty:
        return None

    set_pat = re.compile(r"(\d+)\s*-\s*(\d+)(?:\(\d+\))?")

    def count_tb_from_score(score_str):
        if pd.isna(score_str):
            return 0, 0
        s = str(score_str)
        tb_won = tb_lost = 0
        for a, b in set_pat.findall(s):
            a, b = int(a), int(b)
            if (a, b) == (7, 6):
                tb_won += 1
            elif (a, b) == (6, 7):
                tb_lost += 1
        return tb_won, tb_lost

    rows = []
    for _, r in sub.iterrows():
        tb_w_winner, tb_l_winner = count_tb_from_score(r["Score"])
        if r["Winner_Name"] in players:
            rows.append({"Player": r["Winner_Name"], "TB_Won": tb_w_winner, "TB_Lost": tb_l_winner})
        if r["Loser_Name"] in players:
            rows.append({"Player": r["Loser_Name"], "TB_Won": tb_l_winner, "TB_Lost": tb_w_winner})

    tb_df = pd.DataFrame(rows)
    if tb_df.empty:
        return None

    summary = tb_df.groupby("Player")[["TB_Won", "TB_Lost"]].sum()
    summary["TB_Played"] = summary["TB_Won"] + summary["TB_Lost"]
    summary["TB_WinPct"] = np.where(
        summary["TB_Played"] > 0,
        summary["TB_Won"] / summary["TB_Played"] * 100,
        np.nan
    )

    if summary["TB_Played"].sum() == 0:
        return None

    color_sinner = "#2E7D61"
    color_alcaraz = "#1BB5D8"
    colors = {player1: color_sinner, player2: color_alcaraz}
    
    colors = {player1: color_sinner, player2: color_alcaraz}
    
    fig = Figure(figsize=(10, 6), facecolor="white")
    ax = fig.add_subplot(111, projection="3d")
    ax.set_facecolor("white")

    xs = {player1: 0.0, player2: 1.5}
    dx = 0.8
    z0 = 0.0
    y0 = 0.0
    scale_y = 1.0

    match_found = False
    for p in players:
        if p not in summary.index:
            continue
        match_found = True
        
        tb_played = float(summary.loc[p, "TB_Played"])
        tb_won = int(summary.loc[p, "TB_Won"])
        winpct = float(summary.loc[p, "TB_WinPct"]) if pd.notna(summary.loc[p, "TB_WinPct"]) else 0.0

        x = xs[p]
        dy = tb_played * scale_y
        dz = winpct

        ax.bar3d(
            x, y0, z0,
            dx, dy, dz,
            color=colors.get(p, "grey"),
            edgecolor="black",
            linewidth=1.0,
            shade=True,
            alpha=0.95
        )

        label = f"{get_player_label(p)}\n{winpct:.1f}%\nTB {tb_won}/{int(tb_played)}"
        ax.text(
            x + dx/2,
            y0 + dy + max(0.8, 0.03*dy),
            dz + 2.0,
            label,
            ha="center", va="bottom",
            fontsize=11, weight="bold", color="black"
        )
    
    if not match_found:
        return None

    ax.view_init(elev=22, azim=-55)
    
    ax.set_title(
        "CHI HA GIOCATO MEGLIO DURANTE I TIE-BREAK DEL 2025?",
        fontsize=14, weight="bold", pad=12
    )

    ax.set_xlabel("")
    ax.set_ylabel("Tie-break giocati", labelpad=10)
    ax.set_zlabel("% tie-break vinti", labelpad=10)
    
    ax.set_xticks([xs[player1] + dx/2, xs[player2] + dx/2])
    ax.set_xticklabels([get_player_label(player1), get_player_label(player2)], fontsize=12, weight="bold")
    
    max_tb = float(summary["TB_Played"].max()) * scale_y
    ax.set_ylim(0, max(6, max_tb * 1.25))
    ax.set_zlim(0, 100)
    
    ax.xaxis._axinfo["grid"]["linewidth"] = 0.3
    ax.yaxis._axinfo["grid"]["linewidth"] = 0.3
    ax.zaxis._axinfo["grid"]["linewidth"] = 0.3
    legend_handles = [
        Patch(facecolor=color_sinner, edgecolor="black", label=get_player_label(player1)),
        Patch(facecolor=color_alcaraz, edgecolor="black", label=get_player_label(player2))
    ]
    ax.legend(handles=legend_handles, frameon=True, facecolor="white", edgecolor="black", fontsize=11, loc="upper left")
    
    plt.tight_layout()
    return fig


def plot_wins_by_draw_size(df, player1, player2):
    if "Draw_Size" not in df.columns:
        return None

    def get_wins_by_draw_size(p):
        return df[df["Winner_Name"] == p]["Draw_Size"].value_counts().sort_index()

    s1 = get_wins_by_draw_size(player1)
    s2 = get_wins_by_draw_size(player2)
    
    if s1.empty and s2.empty:
        return None
    
    all_sizes = sorted(list(set(s1.index) | set(s2.index)))
    s1 = s1.reindex(all_sizes, fill_value=0)
    s2 = s2.reindex(all_sizes, fill_value=0)

    fig = Figure(figsize=(14, 6), facecolor="#f9f9f9")
    axes = fig.subplots(1, 2)
    
    c1_bottom = "#FF7F50"  
    c1_top    = "#FFDAB9"  
    
    c2_bottom = "#9AB973"  
    c2_top    = "#E0EED5"  

    x = np.arange(len(all_sizes))
    width = 0.6
    
    for i, val in enumerate(s1.values):
        if val > 0:
            gradient_bar(axes[0], x[i], val, width, color_bottom=c1_bottom, color_top=c1_top)
            
    axes[0].set_title(f"{get_player_label(player1)}", fontsize=13, weight="bold")
    axes[0].set_ylabel("Numero di Vittorie", fontsize=11)
    axes[0].set_xlabel("Numero di giocatori nel torneo", fontsize=11)
    axes[0].set_xticks(x)
    axes[0].set_xticklabels([str(int(s)) for s in all_sizes])
    axes[0].grid(axis="y", linestyle="--", alpha=0.35)
    
    for xi, y in zip(x, s1.values):
        if y > 0:
            axes[0].text(xi, y + 0.1, str(int(y)), ha="center", va="bottom", weight="bold")
            
    axes[0].set_xlim(-0.6, len(all_sizes) - 0.4)
    max1 = s1.values.max() if len(s1) > 0 else 1
    axes[0].set_ylim(0, max1 * 1.15)

    for i, val in enumerate(s2.values):
        if val > 0:
            gradient_bar(axes[1], x[i], val, width, color_bottom=c2_bottom, color_top=c2_top)

    axes[1].set_title(f"{get_player_label(player2)} ", fontsize=13, weight="bold")
    axes[1].set_ylabel("Numero di Vittorie", fontsize=11)
    axes[1].set_xlabel("Numero di giocatori nel torneo", fontsize=11)
    axes[1].set_xticks(x)
    axes[1].set_xticklabels([str(int(s)) for s in all_sizes])
    axes[1].grid(axis="y", linestyle="--", alpha=0.35)
    
    for xi, y in zip(x, s2.values):
        if y > 0:
            axes[1].text(xi, y + 0.1, str(int(y)), ha="center", va="bottom", weight="bold")

    axes[1].set_xlim(-0.6, len(all_sizes) - 0.4)
    max2 = s2.values.max() if len(s2) > 0 else 1
    axes[1].set_ylim(0, max2 * 1.15)

    fig.suptitle("NEL 2025 CHI HA VINTO DI PIÙ NEI VARI TABELLONI?", fontsize=16, weight="bold")
    
    plt.tight_layout()
    return fig


def plot_atp_finals_4tables_scorecard(df, player1, player2):
    dft = df[df["Tourney_Name"].astype(str).str.strip().str.upper() == "ATP FINALS"].copy()

    points_per_win = {"RR": 200, "SF": 400, "F": 500}
    phases = ["RR", "SF", "F"]

    def safe_float(x):
        try:
            if pd.isna(x):
                return 0.0
            return float(x)
        except Exception:
            return 0.0

    def compute_player_stats(p):
        sub = dft[(dft["Winner_Name"] == p) | (dft["Loser_Name"] == p)].copy()
        if sub.empty:
            return None

        svpt = serve_won = ace = dfault = 0.0
        ret_svpt = ret_won = 0.0
        phase_points = {ph: 0 for ph in phases}

        for _, r in sub.iterrows():
            is_win = (r["Winner_Name"] == p)

            if is_win:
                p_svpt = safe_float(r.get("W_ServicePoints"))
                p_1stwon = safe_float(r.get("W_1stWon"))
                p_2ndwon = safe_float(r.get("W_2ndWon"))
                p_ace = safe_float(r.get("W_Ace"))
                p_df = safe_float(r.get("W_DoubleFault"))

                o_svpt = safe_float(r.get("L_ServicePoints"))
                o_1stwon = safe_float(r.get("L_1stWon"))
                o_2ndwon = safe_float(r.get("L_2ndWon"))

                rnd = str(r.get("Round", "")).strip()
                if "Round Robin" in rnd: rnd = "RR"
                if "Semifinals" in rnd: rnd = "SF" 
                if "The Final" in rnd: rnd = "F"

                if rnd in points_per_win:
                    phase_points[rnd] += points_per_win[rnd]

            else:
                p_svpt = safe_float(r.get("L_ServicePoints"))
                p_1stwon = safe_float(r.get("L_1stWon"))
                p_2ndwon = safe_float(r.get("L_2ndWon"))
                p_ace = safe_float(r.get("L_Ace"))
                p_df = safe_float(r.get("L_DoubleFault"))

                o_svpt = safe_float(r.get("W_ServicePoints"))
                o_1stwon = safe_float(r.get("W_1stWon"))
                o_2ndwon = safe_float(r.get("W_2ndWon"))

            if p_svpt > 0:
                svpt += p_svpt
                serve_won += (p_1stwon + p_2ndwon)
                ace += p_ace
                dfault += p_df

            if o_svpt > 0:
                ret_svpt += o_svpt
                o_serve_won = (o_1stwon + o_2ndwon)
                ret_won += max(0.0, o_svpt - o_serve_won)

        serve_pct = (serve_won / svpt * 100.0) if svpt > 0 else 0.0
        return_pct = (ret_won / ret_svpt * 100.0) if ret_svpt > 0 else 0.0
        ace_pct = (ace / svpt * 100.0) if svpt > 0 else 0.0
        df_pct = (dfault / svpt * 100.0) if svpt > 0 else 0.0
        total_points = int(sum(phase_points.values()))

        return {
            "serve_pct": float(serve_pct),
            "return_pct": float(return_pct),
            "ace_pct": float(ace_pct),
            "df_pct": float(df_pct),
            "phase_points": {k: int(v) for k, v in phase_points.items()},
            "total_points": total_points
        }

    s1 = compute_player_stats(player1)
    s2 = compute_player_stats(player2)

    if s1 is None and s2 is None:
        pass 

    PURPLE = "#7A1FFF"
    YELLOW = "#FFD700"

    max_points = max((s1["total_points"] if s1 else 0), (s2["total_points"] if s2 else 0), 1)
    points_scale_max = max(1000, int(np.ceil(max_points / 100.0)) * 100)

    def draw_kpi_table(ax, title, stats, accent_color):
        ax.set_axis_off()
        ax.add_patch(Rectangle((0.02, 0.02), 0.96, 0.96, facecolor="white",
                               edgecolor="black", linewidth=1.2))
        
        ax.add_patch(Rectangle((0.02, 0.86), 0.96, 0.12, facecolor="#F2F2F2",
                               edgecolor="black", linewidth=1.0))
        ax.text(0.5, 0.92, title, ha="center", va="center",
                fontsize=12, weight="bold", color="black", transform=ax.transAxes)

        if stats is None:
            ax.text(0.5, 0.45, "N/D", ha="center", va="center",
                    fontsize=14, weight="bold", color="black", transform=ax.transAxes)
            return

        rows = [
            ("% PUNTI VINTI AL SERVIZIO", stats["serve_pct"]),
            ("% PUNTI VINTI IN RISPOSTA", stats["return_pct"]),
            ("% ACE", stats["ace_pct"]),
            ("% DOPPI FALLI", stats["df_pct"]),
        ]

        y_start = 0.76
        y_step = 0.17
        bar_x0 = 0.55
        bar_w = 0.32
        bar_h = 0.06

        for i, (lab, val) in enumerate(rows):
            yy = y_start - i * y_step

            ax.text(0.06, yy, lab, ha="left", va="center",
                    fontsize=10.2, weight="bold", color="black", transform=ax.transAxes)

            ax.add_patch(Rectangle((bar_x0, yy - bar_h/2), bar_w, bar_h,
                                   facecolor="#EAEAEA", edgecolor="black", linewidth=0.8,
                                   transform=ax.transAxes))
            frac = float(np.clip(val / 100.0, 0, 1))
            ax.add_patch(Rectangle((bar_x0, yy - bar_h/2), bar_w * frac, bar_h,
                                   facecolor=accent_color, edgecolor="none", alpha=0.85,
                                   transform=ax.transAxes))

            ax.text(bar_x0 + bar_w + 0.02, yy, f"{val:.1f}%",
                    ha="left", va="center", fontsize=9.5, weight="bold",
                    color="black", transform=ax.transAxes)

    def draw_points_table(ax, title, stats, accent_color):
        ax.set_axis_off()

        ax.add_patch(Rectangle((0.02, 0.02), 0.96, 0.96, facecolor="white",
                               edgecolor="black", linewidth=1.2))

        ax.add_patch(Rectangle((0.02, 0.86), 0.96, 0.12, facecolor="#F2F2F2",
                               edgecolor="black", linewidth=1.0))
        ax.text(0.5, 0.92, title, ha="center", va="center",
                fontsize=12, weight="bold", color="black", transform=ax.transAxes)

        if stats is None:
            ax.text(0.5, 0.45, "N/D", ha="center", va="center",
                    fontsize=14, weight="bold", color="black", transform=ax.transAxes)
            return

        phase_names = {"RR": "GIRONI", "SF": "SEMIFINALE", "F": "FINALE"}
        rows = [
            ("GIRONI (3 PARTITE)", int(stats["phase_points"].get("RR", 0))),
            ("SEMIFINALE", int(stats["phase_points"].get("SF", 0))),
            ("FINALE", int(stats["phase_points"].get("F", 0))),
            ("TOTALE", int(stats["total_points"]))
        ]

        y_start = 0.74
        y_step = 0.18
        bar_x0 = 0.55
        bar_w = 0.32
        bar_h = 0.07

        for i, (lab, pts) in enumerate(rows):
            yy = y_start - i * y_step

            ax.text(0.06, yy, lab, ha="left", va="center",
                    fontsize=10.6, weight="bold", color="black", transform=ax.transAxes)

            ax.add_patch(Rectangle((bar_x0, yy - bar_h/2), bar_w, bar_h,
                                   facecolor="#EAEAEA", edgecolor="black", linewidth=0.8,
                                   transform=ax.transAxes))

            frac = float(np.clip(pts / points_scale_max, 0, 1))
            ax.add_patch(Rectangle((bar_x0, yy - bar_h/2), bar_w * frac, bar_h,
                                   facecolor=accent_color, edgecolor="none", alpha=0.85,
                                   transform=ax.transAxes))

            ax.text(bar_x0 + bar_w + 0.02, yy, f"{pts}",
                    ha="left", va="center", fontsize=9.8, weight="bold",
                    color="black", transform=ax.transAxes)

    fig = Figure(figsize=(14, 8), facecolor="#f9f9f9")
    axes = fig.subplots(2, 2)
    axes = np.array(axes)

    draw_kpi_table(axes[0, 0], f"{get_player_label(player1)} – KPI", s1, PURPLE)
    draw_kpi_table(axes[0, 1], f"{get_player_label(player2)} – KPI", s2, YELLOW)
    draw_points_table(axes[1, 0], f"{get_player_label(player1)} – PUNTI ATP", s1, PURPLE)
    draw_points_table(axes[1, 1], f"{get_player_label(player2)} – PUNTI ATP", s2, YELLOW)

    fig.suptitle(
        "RENDIMENTO DI SINNER E ALCARAZ ALLE ATP FINALS 2025",
        fontsize=16, weight="bold", y=0.98
    )

    plt.tight_layout(rect=[0, 0, 1, 0.95])
    return fig


def plot_set_scores_bo3_bo5_wl_panels(df, player1, player2):

    needed = {"Winner_Name", "Loser_Name", "Best_of", "Score"}
    missing = needed - set(df.columns)
    if missing:
        return None

    players = [player1, player2]
    cats = ["6-0", "6-1", "6-2", "6-3", "6-4", "7-5", "7-6"]

    COLOR_BO3 = "#8B2D2D"  
    COLOR_BO5 = "#94EEF4" 

    set_pat = re.compile(r"(\d+)\s*-\s*(\d+)(?:\(\d+\))?")

    def parse_sets(score):
        if score is None or (isinstance(score, float) and np.isnan(score)):
            return []
        s = str(score).upper().strip()
        if "W/O" in s or s == "WO" or "RET" in s:
            return []
        out = []
        for a, b in set_pat.findall(s):
            try:
                out.append((int(a), int(b)))
            except:
                pass
        return out

    def normalize_winning_set(w, l):
        if w == 6 and l in (0, 1, 2, 3, 4):
            return f"6-{l}"
        if w == 7 and l in (5, 6):
            return f"7-{l}"
        return None

    counts = {
        p: {
            "W": {"BO3": {c: 0 for c in cats}, "BO5": {c: 0 for c in cats}},
            "L": {"BO3": {c: 0 for c in cats}, "BO5": {c: 0 for c in cats}},
        } for p in players
    }

    sub = df[(df["Winner_Name"].isin(players)) | (df["Loser_Name"].isin(players))].copy()
    sub["Best_of"] = pd.to_numeric(sub["Best_of"], errors="coerce")

    for _, r in sub.iterrows():
        bo = r["Best_of"]
        if bo not in (3, 5):
            continue
        bo_key = "BO3" if int(bo) == 3 else "BO5"

        w = str(r["Winner_Name"]).strip()
        l = str(r["Loser_Name"]).strip()
        sets = parse_sets(r["Score"])
        if not sets:
            continue

        for a, b in sets:
            if a == b:
                continue

            if a > b:
                cat = normalize_winning_set(a, b)
                if cat in cats:
                    if w in players:
                        counts[w]["W"][bo_key][cat] += 1
                    if l in players:
                        counts[l]["L"][bo_key][cat] += 1
            else:
                cat = normalize_winning_set(b, a)
                if cat in cats:
                    if l in players:
                        counts[l]["W"][bo_key][cat] += 1
                    if w in players:
                        counts[w]["L"][bo_key][cat] += 1

    all_vals = []
    for p in players:
        for wl in ("W", "L"):
            for bo_key in ("BO3", "BO5"):
                all_vals += list(counts[p][wl][bo_key].values())
    x_max = max(all_vals + [1])
    xlim = (0, int(np.ceil(x_max * 1.15)))

    def draw_panel(ax, player, wl):
        y = np.arange(len(cats))
        h = 0.34

        vals_bo3 = np.array([counts[player][wl]["BO3"][c] for c in cats], dtype=int)
        vals_bo5 = np.array([counts[player][wl]["BO5"][c] for c in cats], dtype=int)

        ax.barh(
            y - h/2, vals_bo3,
            height=h,
            color=COLOR_BO3,
            edgecolor="black",
            linewidth=0.9,
            label="BO3"
        )

        ax.barh(
            y + h/2, vals_bo5,
            height=h,
            color=COLOR_BO5,
            edgecolor="black",
            linewidth=0.9,
            label="BO5"
        )

        for yi, v in enumerate(vals_bo3):
            if v > 0:
                ax.text(v + 0.15, yi - h/2, str(v),
                        va="center", ha="left",
                        fontsize=9, weight="bold", color="black")
        for yi, v in enumerate(vals_bo5):
            if v > 0:
                ax.text(v + 0.15, yi + h/2, str(v),
                        va="center", ha="left",
                        fontsize=9, weight="bold", color="black")

        ax.set_yticks(y)
        ax.set_yticklabels(cats, fontsize=10, weight="bold", color="black")
        ax.invert_yaxis()

        ax.set_xlim(*xlim)
        ax.grid(axis="x", linestyle="--", alpha=0.25)

        title_wl = "SET VINTI" if wl == "W" else "SET PERSI"
        ax.set_title(f"{get_player_label(player)} – {title_wl}",
                     fontsize=12, weight="bold", pad=8)

        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.tick_params(axis="x", labelsize=9, colors="black")
        ax.tick_params(axis="y", length=0)

    accent_sinner = "#7A1FFF"
    accent_alcaraz = "#FFD700"

    fig = Figure(figsize=(16, 9), facecolor="#f9f9f9")
    axes = fig.subplots(2, 2)

    draw_panel(axes[0, 0], player1, "W")
    draw_panel(axes[0, 1], player2, "W")
    draw_panel(axes[1, 0], player1, "L")
    draw_panel(axes[1, 1], player2, "L")

    fig.suptitle(
        "DISTRIBUZIONE DEI RISULTATI DEI SET DEL 2025",
        fontsize=15, weight="bold", y=0.98
    )

    legend_handles = [
        Patch(facecolor=COLOR_BO3, edgecolor="black", label="BO3"),
        Patch(facecolor=COLOR_BO5, edgecolor="black", label="BO5"),
    ]
    fig.legend(
        handles=legend_handles,
        loc="upper center",
        ncol=2,
        frameon=False,
        fontsize=11,
        bbox_to_anchor=(0.5, 0.94)
    )

    plt.tight_layout(rect=[0, 0, 1, 0.93])
    return fig


def plot_sfortuna_fortuna_retiri_dotplot(df, player1, player2):
    needed = {"Winner_Name", "Loser_Name", "Score", "Tourney_Name"}
    missing = needed - set(df.columns)
    if missing:
        return None

    players = [player1, player2]

    d = df.copy()
    d["Score"] = d["Score"].astype(str)

    ret = d[
        d["Score"].str.upper().str.contains("RET", na=False) &
        ~d["Score"].str.upper().str.contains("W/O", na=False) &
        ~(d["Score"].str.upper().str.strip() == "WO")
    ].copy()

    if ret.empty:
        return None

    if "Tourney_Date" in ret.columns:
        ret["Tourney_Date"] = pd.to_datetime(ret["Tourney_Date"], errors="coerce")
        ret = ret.sort_values(["Tourney_Date", "Tourney_Name"], na_position="last")
    else:
        ret = ret.reset_index().sort_values("index").drop(columns=["index"])

    ret = ret.reset_index(drop=True)
    ret["_idx"] = np.arange(1, len(ret) + 1)

    spacing = 6.0  # further increased spacing

    colors = {player1: "#99CBFF", player2: "#FC0FC0"}
    y_pos = {player1: 1.0, player2: 0.0}

    def opp_and_label(row, p):
        if row["Winner_Name"] == p:
            opp = str(row["Loser_Name"]).strip()
        else:
            opp = str(row["Winner_Name"]).strip()
        tour = str(row["Tourney_Name"]).strip()
        return f"{opp}\n{tour}"

        return f"{opp}\n{tour}"

    fig = Figure(figsize=(14, 5.5), facecolor="#f9f9f9")
    ax = fig.subplots()
    ax.set_facecolor("#f9f9f9")

    box_props = dict(boxstyle="round,pad=0.18", fc="white", ec="black", lw=0.6)

    for p in players:
        y = y_pos[p]
        sub = ret[(ret["Winner_Name"] == p) | (ret["Loser_Name"] == p)].copy()
        if sub.empty:
            continue

        x = sub["_idx"].to_numpy(dtype=float) * spacing

        is_loss_by_ret = (sub["Loser_Name"] == p).to_numpy(dtype=bool)
        is_win_by_ret  = (sub["Winner_Name"] == p).to_numpy(dtype=bool)

        x_left  = x[is_loss_by_ret]
        x_right = x[is_win_by_ret]

        if len(x_left) > 0:
            ax.scatter(-x_left, np.full(len(x_left), y), s=90,
                       color=colors[p], edgecolor="black", linewidth=0.8, alpha=0.95)

        if len(x_right) > 0:
            ax.scatter(x_right, np.full(len(x_right), y), s=90,
                       color=colors[p], edgecolor="black", linewidth=0.8, alpha=0.95)

        dy = -0.14 if p == player1 else 0.14
        va = "top" if p == player1 else "bottom"

        for _, row in sub[is_loss_by_ret].iterrows():
            xi = -float(row["_idx"]) * spacing
            ax.text(
                xi, y + dy,
                opp_and_label(row, p),
                ha="center", va=va,
                fontsize=7.6,
                bbox=box_props
            )

        for _, row in sub[is_win_by_ret].iterrows():
            xi = float(row["_idx"]) * spacing
            ax.text(
                xi, y + dy,
                opp_and_label(row, p),
                ha="center", va=va,
                fontsize=7.6,
                bbox=box_props
            )

    ax.axvline(0, color="black", linewidth=1.2)

    max_idx = int(ret["_idx"].max()) if not ret.empty else 1
    lim = (max_idx + 0.8) * spacing
    ax.set_xlim(-lim, lim)

    tick_indices = np.arange(-max_idx, max_idx + 1, 1)
    ax.set_xticks(tick_indices * spacing)
    ax.set_xticklabels([str(abs(i)) for i in tick_indices])

    ax.set_yticks([y_pos[player1], y_pos[player2]])
    labels = [get_player_label(player1), get_player_label(player2)]
    ax.set_yticklabels(labels, fontsize=13, weight="bold")
    for tick, p in zip(ax.get_yticklabels(), [player1, player2]):
        tick.set_color(colors[p])

    ax.grid(axis="x", linestyle="--", alpha=0.25)

    ax.text(0.02, 1.01, "SFORTUNA (ritiro proprio → match perso)",
            transform=ax.transAxes, ha="left", va="bottom",
            fontsize=11, weight="bold", color="black")
    ax.text(0.98, 1.01, "FORTUNA (ritiro avversario → match vinto)",
            transform=ax.transAxes, ha="right", va="bottom",
            fontsize=11, weight="bold", color="black")

    fig.suptitle(
        "SFORTUNA E FORTUNA PER I DUE GIOCATORI NEL 2025",
        fontsize=18,
        weight="bold",
        y=0.985
    )

    ax.set_xlabel("Match", fontsize=12)

    for spine in ax.spines.values():
        spine.set_visible(False)

    plt.tight_layout(rect=[0, 0.05, 1, 0.95])
    return fig


IOC_COORDS = {
    "ARG": (-64, -34), "BRA": (-53, -10), "CAN": (-100, 58),
    "CHI": (-71, -30), "COL": (-73, 4),   "MEX": (-102, 23),
    "PER": (-74, -9),  "USA": (-98, 39),  "URU": (-56, -33),
    
    "AUS": (135, -25), "CHN": (103, 36),  "JPN": (139, 36),
    "KAZ": (67, 48),   "KOR": (128, 36),  "IND": (78, 22),
    
    "POR": (-12, 38),   
    "ESP": (-6, 39),    
    "FRA": (0, 46),     
    "GBR": (-5, 56),    
    "NED": (4, 53),     
    "BEL": (3, 49.5),   
    "GER": (10, 51.5),  
    "SUI": (7, 45.5),   
    "ITA": (13, 40),    
    "AUT": (15, 47),    
    "CZE": (16, 50.5),
    "POL": (20, 53),    
    "DEN": (9, 57),     
    "NOR": (7, 62),
    "SWE": (16, 62),
    "FIN": (27, 65),
    
    "HUN": (19, 46),
    "SVK": (20, 49),
    "CRO": (16, 43.5),
    "SRB": (22, 43),    
    "BGR": (26, 42),
    "GRE": (22, 37),    
    "ROU": (26, 46),
    "UKR": (32, 49),
    "BLR": (29, 54),
    "RUS": (45, 58),    
    "TUR": (36, 39),

    "RSA": (24, -29), "MAR": (-6, 31), "TUN": (9, 33)
}

def draw_pie_marker(ax, x, y, ratios, size, colors):
    total = sum(ratios)
    if total == 0: return
    ratios_norm = [v / total for v in ratios]
    cumsum = np.cumsum(ratios_norm)
    angles = [0] + [360 * val for val in cumsum]
    start_angle = 90
    for i, color in enumerate(colors):
        theta1 = start_angle + angles[i]
        theta2 = start_angle + angles[i+1]
        wedge = Wedge((x, y), size, theta1, theta2, 
                      facecolor=color, edgecolor="white", linewidth=0.5, zorder=10)
        ax.add_patch(wedge)

def plot_geo_opponent_pies_geopandas(df, player_name):
    col_w_ioc = "Winner_Nat" if "Winner_Nat" in df.columns else "Winner_Assoc"
    col_l_ioc = "Loser_Nat"  if "Loser_Nat" in df.columns  else "Loser_Assoc"

    if col_w_ioc not in df.columns:
        return None

    opponents = {} 
    sub = df[(df["Winner_Name"] == player_name) | (df["Loser_Name"] == player_name)]
    if sub.empty:
        return None

    for _, row in sub.iterrows():
        if row["Winner_Name"] == player_name:
            nation = str(row[col_l_ioc]).strip().upper()
            if nation not in opponents: opponents[nation] = [0, 0]
            opponents[nation][0] += 1
        else:
            nation = str(row[col_w_ioc]).strip().upper()
            if nation not in opponents: opponents[nation] = [0, 0]
            opponents[nation][1] += 1

    fig = Figure(figsize=(18, 10))
    ax = fig.subplots()
    
    try:
        world = gpd.read_file(gpd.datasets.get_path('naturalearth_lowres'))
        if 'name' in world.columns: world = world[(world['name'] != "Antarctica")]
    except:
        try:
            url = "https://naciscdn.org/naturalearth/110m/cultural/ne_110m_admin_0_countries.zip"
            world = gpd.read_file(url)
            if 'NAME' in world.columns: world = world[(world['NAME'] != "Antarctica")]
            elif 'ADMIN' in world.columns: world = world[(world['ADMIN'] != "Antarctica")]
        except Exception as e:
            st.error(f"Errore caricamento mappa: {e}")
            return None
    
    world.plot(ax=ax, color='#EEEEEE', edgecolor='white', linewidth=0.5)
    ax.set_facecolor("white")

    colors = ["#28a745", "#dc3545"]
    found_any = False
    
    sorted_opponents = sorted(opponents.items(), key=lambda item: sum(item[1]), reverse=True)

    for ioc, (wins, losses) in sorted_opponents:
        if ioc in IOC_COORDS:
            lon, lat = IOC_COORDS[ioc]
            total = wins + losses
            
            radius = 2.0 + (total ** 0.5) * 0.6
            
            draw_pie_marker(ax, lon, lat, [wins, losses], radius, colors)
            
            label_y_offset = radius + 0.5
            
            ax.text(lon, lat - label_y_offset, f"{ioc}", 
                    ha="center", va="top", fontsize=7, weight="bold", 
                    color="#222", zorder=20)
            
            found_any = True
            
    ax.set_title(f"VITTORIE E SCONFITTE DEL 2025 DAL PUNTO DI VISTA DELLA NAZIONALITÀ: {get_player_label(player_name).upper()}", 
                 fontsize=18, weight="bold", pad=20)
    ax.set_axis_off()
    ax.set_ylim(-60, 85)

    from matplotlib.lines import Line2D
    legend_elements = [
        Line2D([0], [0], marker='o', color='w', label='Vittorie', markerfacecolor=colors[0], markersize=10),
        Line2D([0], [0], marker='o', color='w', label='Sconfitte', markerfacecolor=colors[1], markersize=10)
    ]
    ax.legend(handles=legend_elements, loc='lower left', frameon=False, fontsize=12)

    return fig



def start_background_jobs():
    log_ingestion = open("/app/data/debug_ingestion.log", "w")
    subprocess.Popen(["python", "-u", "/app/scripts/ingestion.py"], stdout=log_ingestion, stderr=log_ingestion)
    
    time.sleep(10) 

    log_streaming = open("/app/data/debug_streaming.log", "w")
    subprocess.Popen(["python", "-u", "/app/scripts/streaming_job.py"], stdout=log_streaming, stderr=log_streaming)
    
    log_batch = open("/app/data/debug_batch.log", "w")
    subprocess.Popen(["python", "-u", "/app/scripts/batch_job.py"], stdout=log_batch, stderr=log_batch)

    
def reset_simulation():
    os.system("pkill -f ingestion.py")
    os.system("pkill -f streaming_job.py")
    os.system("pkill -f batch_job.py")
    try:
        client = MongoClient("mongodb://mongo:27017/")
        db = client["tennis_db"]
        db["realtime_stats"].drop() 
        db["realtime_matches"].drop() 
        db["batch_model_metrics"].drop()
        client.close()
        print("🧹 Database svuotato completamente.")
    except Exception as e:
        print(f"Errore pulizia DB: {e}")

    try:
        admin_client = KafkaAdminClient(bootstrap_servers="kafka:9092")
        admin_client.delete_topics(["tennis-live"])
        print("🗑️ Topic Kafka 'tennis-live' eliminato.")
        admin_client.close()
    except Exception as e:
        print(f"⚠️ Errore eliminazione topic Kafka (forse non esiste): {e}")

    st.session_state['simulation_active'] = False
    
    time.sleep(1)



def render_servizio(df, title):
    st.header(f"🚀 {title}")
    st.markdown("*Analisi della battuta*")
    st.divider()

    st.subheader("📊 % Prime in Campo e Punti Vinti")
    if not df is None and not df.empty:
        fig = plot_first_serve_bars_clean(df, ["Jannik Sinner", "Carlos Alcaraz"])
        if fig: 
            st.pyplot(fig, use_container_width=True)
            plt.close(fig)
        else: st.info("Dati servizio non disponibili.")
    else: pass
    st.divider()

    st.subheader("⚔️ Focus Prima di Servizio (H2H)")
    if not df is None and not df.empty:
        fig = plot_first_serve_h2h_scorecard(df, "Jannik Sinner", "Carlos Alcaraz")
        if fig: 
            st.pyplot(fig, use_container_width=True)
            plt.close(fig)
    st.divider()

    st.subheader("📉 Efficienza Seconda di Servizio")
    if not df is None and not df.empty:
        fig = plot_second_serve_efficiency_boxplot_by_surface_colors(df, "Jannik Sinner", "Carlos Alcaraz")
        if fig: 
            st.pyplot(fig, use_container_width=True)
            plt.close(fig)
    st.divider()

    st.subheader("🔹 Focus Seconda di Servizio (H2H)")
    if not df is None and not df.empty:
        fig = plot_second_serve_efficiency_h2h_scatter(df, "Jannik Sinner", "Carlos Alcaraz")
        if fig: 
            st.pyplot(fig, use_container_width=True)
            plt.close(fig)
    st.divider()

    st.subheader("📏 Correlazione Altezza vs Punti Servizio")
    if not df is None and not df.empty:
        fig = plot_service_winpct_strip(df, ["Jannik Sinner", "Carlos Alcaraz"])
        if fig: 
            st.pyplot(fig, use_container_width=True)
            plt.close(fig)
    st.divider()

    st.subheader("📈 Trend Stagionale Ace e Doppi Falli")
    if not df is None and not df.empty:
        fig = plot_ace_df_four_area_charts_all_matches(df, "Jannik Sinner", "Carlos Alcaraz")
        if fig: 
            st.pyplot(fig, use_container_width=True)
            plt.close(fig)
    st.divider()

    st.subheader("🎾 Ace e Doppi Falli (H2H)")
    if not df is None and not df.empty:
        fig = plot_h2h_ace_df_bars_horizontal_per_match(df, "Jannik Sinner", "Carlos Alcaraz")
        if fig: 
            st.pyplot(fig, use_container_width=True)
            plt.close(fig)

def render_superfici(df, df_filtered, title):
    st.header(f"🌍 {title}")
    st.markdown("*Dove hanno vinto e importanza dei tornei*")
    st.divider()

    st.subheader("🏆 Vittorie Totali per Superficie")
    if not df_filtered.empty:
        fig = plot_vertical_players_3bars_stacked(df_filtered, ["Jannik Sinner", "Carlos Alcaraz"])
        if fig: 
            st.pyplot(fig, use_container_width=True)
            plt.close(fig)
    else: pass
    st.divider()

    st.subheader("⚔️ Scontri Diretti per Superficie")
    if not df is None and not df.empty:
        fig = plot_h2h_wins_by_surface(df, "Jannik Sinner", "Carlos Alcaraz")
        if fig: 
            st.pyplot(fig, use_container_width=True)
            plt.close(fig)
    st.divider()

    st.subheader("🏟️ Indoor vs Outdoor")
    if not df is None and not df.empty:
        fig = plot_win_loss_indoor_outdoor_counts(df, ["Jannik Sinner", "Carlos Alcaraz"])
        if fig: 
            st.pyplot(fig, use_container_width=True)
            plt.close(fig)
    st.divider()

    st.subheader("📋 Risultati Tornei")
    if not df is None and not df.empty:
        fig = plot_tourney_summary_two_tables(df, ["Jannik Sinner", "Carlos Alcaraz"])
        if fig: 
            st.pyplot(fig, use_container_width=True)
            plt.close(fig)
    st.divider()

    st.subheader("📊 Vittorie per Dimensione Tabellone")
    if not df_filtered.empty:
        fig = plot_wins_by_draw_size(df_filtered, "Jannik Sinner", "Carlos Alcaraz")
        if fig: 
            st.pyplot(fig, use_container_width=True)
            plt.close(fig)
    st.divider()

    st.subheader("⏳ Minuti Giocati nei 4 Slam")
    if not df is None and not df.empty:
        fig = plot_4slams_minutes_single_image(df, "Jannik Sinner", "Carlos Alcaraz")
        if fig: 
            st.pyplot(fig, use_container_width=True)
            plt.close(fig)
    st.divider()

    if "SUPERFICI" in title:
        st.subheader("🏁 Focus ATP Finals")
        if not df_filtered.empty:
            fig = plot_atp_finals_4tables_scorecard(df_filtered, "Jannik Sinner", "Carlos Alcaraz")
            if fig: 
                st.pyplot(fig, use_container_width=True)
                plt.close(fig)
    st.divider()

    st.subheader("🗺️ Globalità Vittorie")
    if not df_filtered.empty:
        col_m1, col_m2 = st.columns(2)
        with col_m1:
            st.markdown("**Jannik Sinner**")
            fig_m1 = plot_geo_opponent_pies_geopandas(df_filtered, "Jannik Sinner")
            if fig_m1: 
                st.pyplot(fig_m1, use_container_width=True)
                plt.close(fig_m1)
        with col_m2:
            st.markdown("**Carlos Alcaraz**")
            fig_m2 = plot_geo_opponent_pies_geopandas(df_filtered, "Carlos Alcaraz")
            if fig_m2: 
                st.pyplot(fig_m2, use_container_width=True)
                plt.close(fig_m2)

def render_mentalita(df, df_filtered, title):
    plt.close("all")
    st.header(f"🧠 {title}")
    st.markdown("*Chi è più efficiente nei momenti decisivi?*")
    st.divider()
    st.subheader("🧊 Tie-Break Analysis")
    if not df_filtered.empty:
        fig = plot_tiebreak_3d_blocks(df_filtered, "Jannik Sinner", "Carlos Alcaraz")
        if fig: 
            st.pyplot(fig, use_container_width=True)
            plt.close(fig)
    else: pass
    st.divider()

    st.subheader("⚠️ Palle Break Stagionali")
    if not df is None and not df.empty:
        fig = plot_breakpoints_violin(df, ["Jannik Sinner", "Carlos Alcaraz"])
        if fig: 
            st.pyplot(fig, use_container_width=True)
            plt.close(fig)
    st.divider()

    st.subheader("🏋️ Palle Break (H2H)")
    if not df is None and not df.empty:
        fig = plot_breakpoints_h2h_dumbbell(df, ["Jannik Sinner", "Carlos Alcaraz"])
        if fig: 
            st.pyplot(fig, use_container_width=True)
            plt.close(fig)
    st.divider()

    st.subheader("⚔️ Capacità di Vincere in Meno Set")
    if not df is None and not df.empty:
        fig = plot_wins_by_sets_percentage(df, ["Jannik Sinner", "Carlos Alcaraz"])
        if fig: 
            st.pyplot(fig, use_container_width=True)
            plt.close(fig)
    st.divider()

    st.subheader("🍀 Fattore Fortuna & Sfortuna")
    if not df_filtered.empty:
        fig = plot_sfortuna_fortuna_retiri_dotplot(df_filtered, "Jannik Sinner", "Carlos Alcaraz")
        if fig: 
            st.pyplot(fig, use_container_width=True)
            plt.close(fig)

def render_costanza(df, df_filtered, title):
    plt.close("all")
    st.header(f"🛡️ {title}")
    st.markdown("*Continuità, Ranking e Tipologia Avversari*")
    st.divider()
    st.subheader("📈 Corsa al Numero 1")
    if not df is None and not df.empty:
        fig = plot_rank_points_evolution(df, ["Jannik Sinner", "Carlos Alcaraz"])
        if fig: 
            st.pyplot(fig, use_container_width=True)
            plt.close(fig)
    else: pass
    st.divider()

    st.subheader("🏆 Rendimento Contro Top 10 & Non Top 10")
    if not df is None and not df.empty:
        fig = plot_wl_top10_vs_nontop10_area(df, ["Jannik Sinner", "Carlos Alcaraz"])
        if fig: 
            st.pyplot(fig, use_container_width=True)
            plt.close(fig)
    st.divider()

    st.subheader("🎾 Distribuzione Punteggi per Set")
    if not df_filtered.empty:
        fig = plot_set_scores_bo3_bo5_wl_panels(df_filtered, "Jannik Sinner", "Carlos Alcaraz")
        if fig: 
            st.pyplot(fig, use_container_width=True)
            plt.close(fig)
    st.divider()

    st.subheader("⏱️ Resistenza")
    if not df is None and not df.empty:
        fig = plot_resistenza_divergente(df, ["Jannik Sinner", "Carlos Alcaraz"])
        if fig: 
            st.pyplot(fig, use_container_width=True)
            plt.close(fig)
    st.divider()

    st.subheader("🤚 Efficacia contro Mancini vs Destrimani")
    if not df is None and not df.empty:
        fig = plot_winrate_vs_hand_heatmap(df, ["Jannik Sinner", "Carlos Alcaraz"])
        if fig: 
            st.pyplot(fig, use_container_width=True)
            plt.close(fig)
    st.divider()

    st.subheader("📏 Performance vs Giovani o Veterani")
    if not df is None and not df.empty:
        fig = plot_wl_vs_older_younger_ruler(df, ["Jannik Sinner", "Carlos Alcaraz"])
        if fig: 
            st.pyplot(fig, use_container_width=True)
            plt.close(fig)
    st.divider()

    if "COSTANZA" in title:
        st.subheader("🌱 Vittorie in base al Seed")
        if not df is None and not df.empty:
            fig = plot_wins_by_seed(df, ["Jannik Sinner", "Carlos Alcaraz"])
            if fig: 
                st.pyplot(fig, use_container_width=True)
                plt.close(fig)

def render_previsioni(batch_metric, title):
    st.header(f"🔮 {title}")
    st.markdown("*Quote Antepost e Modelli Predittivi Machine Learning*")
    st.divider()
    
    plt.close("all")

    st.subheader("💰 Quote Antepost Slam")
    render_odds_table(batch_metric)
    st.divider()
    
    st.subheader("🧠 Batch Layer: Machine Learning Results")
    if batch_metric:
        tab_ml, tab_preds = st.tabs(["📊 Performance Modello", "🔮 Previsioni 2026"])
        
        with tab_ml:
            acc = batch_metric.get('accuracy', 0)
            st.success(f"✅ Modello Spark Addestrato. Accuratezza: {acc*100:.2f}%")
            cm = batch_metric.get('confusion_matrix', {})
            if cm:
                st.markdown("##### 📉 Matrice di Confusione")
                cm_data = {
                    "Reale: Sconfitta": [f"TN: {cm.get('TN',0)}", f"FN: {cm.get('FN',0)}"],
                    "Reale: Vittoria":  [f"FP: {cm.get('FP',0)}", f"TP: {cm.get('TP',0)}"]
                }
                st.table(pd.DataFrame(cm_data, index=["Pred: Sconfitta", "Pred: Vittoria"]))
        
        with tab_preds:
            preds_2026 = batch_metric.get('predictions_2026', [])
            if preds_2026:
                df_preds = pd.DataFrame(preds_2026)
                def highlight_winner(val):
                    color = '#d4edda' if val == 'SINNER' else '#f8d7da' 
                    return f'background-color: {color}; color: black; font-weight: bold;'
                st.dataframe(
                    df_preds.style.applymap(highlight_winner, subset=['FAVORITO'])
                                  .format("{:.2f}", subset=['Q. SINNER', 'Q. ALCARAZ']),
                    use_container_width=True, hide_index=True
                )
            else:
                st.info("Previsioni 2026 in elaborazione...")
    else:
        st.info("Modello ML in training... attendere Batch Job.")

def reset_simulation():
    os.system("pkill -f ingestion.py")
    os.system("pkill -f streaming_job.py")
    os.system("pkill -f batch_job.py")
    
    try:
        client = MongoClient("mongodb://mongo:27017/")
        db = client["tennis_db"]
        db["realtime_matches"].drop()
        db["batch_model_metrics"].drop()
        client.close()
    except Exception as e:
        print(f"Errore pulizia MongoDB: {e}")

    try:
        admin_client = KafkaAdminClient(
            bootstrap_servers="kafka:9092", 
            client_id='admin_reset'
        )
        admin_client.delete_topics(["tennis-live"])
        admin_client.close()
        time.sleep(2) 
    except Exception as e:
        print(f"Errore pulizia Kafka (potrebbe essere normale se topic non esistono): {e}")

    st.session_state['simulation_active'] = False
    time.sleep(1)

def start_background_jobs():
    log_ing = open("/app/data/debug_ingestion.log", "w")
    subprocess.Popen(["python", "-u", "/app/scripts/ingestion.py"], stdout=log_ing, stderr=log_ing)
    
    time.sleep(5) 
    
    log_str = open("/app/data/debug_streaming.log", "w")
    subprocess.Popen(["python", "-u", "/app/scripts/streaming_job.py"], stdout=log_str, stderr=log_str)
    
    log_bat = open("/app/data/debug_batch.log", "w")
    subprocess.Popen(["python", "-u", "/app/scripts/batch_job.py"], stdout=log_bat, stderr=log_bat)

def render_current_page(selection, df, df_filtered, batch_metric, PAGES):
    plt.close("all")
    
    if selection == "SERVIZIO":
        render_servizio(df, PAGES["SERVIZIO"])
        
    elif selection == "SUPERFICI":
        render_superfici(df, df_filtered, PAGES["SUPERFICI"])
        
    elif selection == "MENTALITA":
        render_mentalita(df, df_filtered, PAGES["MENTALITA"])
        
    elif selection == "COSTANZA":
        render_costanza(df, df_filtered, PAGES["COSTANZA"])
        
    elif selection == "PREVISIONI":
        render_previsioni(batch_metric, PAGES["PREVISIONI"])


def show_dashboard():
    plt.close("all")

    c1, c2 = st.columns([6, 1])
    c1.title("🎾 Live Control Room")
    if c2.button("⏹️ RESET"):
        reset_simulation()
        st.rerun()

    try:
        client = MongoClient("mongodb://mongo:27017/")
        db = client["tennis_db"]
        data = list(db["realtime_matches"].find({}, {"_id": 0}))
        batch_metric = db["batch_model_metrics"].find_one(sort=[("_id", -1)])
    except Exception as e:
        st.error(f"Errore Database: {e}")
        return

    df = pd.DataFrame(data) if data else pd.DataFrame()
    df_filtered = pd.DataFrame()
    if not df.empty:
        targets = ["Jannik Sinner", "Carlos Alcaraz"]
        df_filtered = df[df["Winner_Name"].isin(targets) | df["Loser_Name"].isin(targets)]
    else:
        st.info("📡 In attesa di dati dallo stream Kafka...")

    st.sidebar.title("Navigazione")
    
    PAGES = {
        "SERVIZIO": "SERVIZIO",
        "SUPERFICI": "SUPERFICI & GRANDI TORNEI",
        "MENTALITA": "MENTALITÀ & CLUTCH",
        "COSTANZA": "COSTANZA & ANALISI AVVERSARI",
        "PREVISIONI": "PREVISIONI & ODDS"
    }
    
    selection = st.sidebar.radio(
        "Vai a:", 
        list(PAGES.keys()), 
        format_func=lambda x: PAGES[x]
    )
    
    st.sidebar.markdown("---")
    realtime_mode = st.sidebar.checkbox("📡 Aggiornamento Real-Time", value=True)

    render_current_page(selection, df, df_filtered, batch_metric, PAGES)

    if realtime_mode:
        time.sleep(3)
        st.rerun()

def show_landing_page():
    st.markdown("<h1 style='text-align: center;'>🎾 Tennis Big Data Project</h1>", unsafe_allow_html=True)
    
    current_dir = os.path.dirname(os.path.abspath(__file__))
    img_path = os.path.join(current_dir, "../data/sfondo.jpeg")

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if os.path.exists(img_path):
            st.image(img_path, use_container_width=True)
        else:
            st.warning(f"Immagine non trovata: {img_path}")

        st.divider()

        if st.button("🚀 AVVIA SIMULAZIONE COMPLETA", use_container_width=True):
            with st.status("Avvio sistema...", expanded=True) as status:
                st.write("🧹 Pulizia preventiva...")
                reset_simulation()
                time.sleep(1)
                st.write("📡 Avvio Pipeline...")
                start_background_jobs()
                time.sleep(5)
                status.update(label="Sistema Online!", state="complete")
            
            st.session_state['simulation_active'] = True
            st.rerun()

if __name__ == "__main__":
    matplotlib.use('Agg')
    
    if 'simulation_active' not in st.session_state:
        st.session_state['simulation_active'] = False

    if st.session_state['simulation_active']:
        show_dashboard()
    else:
        show_landing_page()