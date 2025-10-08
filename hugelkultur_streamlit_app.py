
import matplotlib.pyplot as plt
import numpy as np
import streamlit as st

st.set_page_config(page_title="Hügelkultur – Simple Schematic", layout="centered")
st.title("Hügelkultur (Simple Schematic)")
st.caption("A quick visual of how a hügelkultur mound helps manage rainwater.")

# --- Draw a simple schematic with matplotlib ---
fig, ax = plt.subplots(figsize=(8, 4))

# Ground line
ax.plot([0, 10], [2, 2], linewidth=3)

# Hügelkultur mound (triangle)
mound_x = [3, 5, 7]
mound_y = [2, 4, 2]
ax.fill(mound_x, mound_y, alpha=0.6)

# Wood/organic layers (simple hatching effect)
for h in np.linspace(2.2, 3.8, 6):
    ax.plot([3.2, 6.8], [h, h], alpha=0.3)

# Raindrops
for x in np.linspace(1, 9, 12):
    ax.annotate("", xy=(x, 4.2), xytext=(x, 5.5),
                arrowprops=dict(arrowstyle="-", lw=1))
    ax.text(x, 5.7, "💧", ha="center", va="center", fontsize=10)

# Infiltration arrows (downward into mound)
for x in [4.0, 5.0, 6.0]:
    ax.annotate("", xy=(x, 2.4), xytext=(x, 3.6),
                arrowprops=dict(arrowstyle="-|>", lw=2))

# Slow spread arrows (lateral within mound)
ax.annotate("", xy=(4.2, 3.1), xytext=(3.3, 3.1),
            arrowprops=dict(arrowstyle="-|>", lw=1.8))
ax.annotate("", xy=(5.8, 3.1), xytext=(6.7, 3.1),
            arrowprops=dict(arrowstyle="-|>", lw=1.8))

# Reduced runoff arrow toward road
ax.annotate("reduced runoff to road", xy=(8.5, 2.15), xytext=(8.5, 3.2),
            arrowprops=dict(arrowstyle="-|>", lw=2))
ax.text(8.5, 1.7, "road ↓", ha="center", va="top")

# Labels
ax.text(5, 4.2, "mulch + soil", ha="center", fontsize=10)
ax.text(5, 3.2, "wood/organic core\n('sponge')", ha="center", fontsize=10)

ax.set_xlim(0, 10)
ax.set_ylim(1.2, 6)
ax.axis("off")

st.pyplot(fig)

st.markdown("""
**How it helps during rain:**
- **Catches water:** The mound and mulch slow raindrops so less water runs off.
- **Soaks water in:** The wood/organic core acts like a **sponge**, storing moisture.
- **Spreads water:** Pores and channels move water sideways and downward into soil.
- **Protects roads/soil:** With less fast runoff, there’s **less erosion** on nearby dirt roads.
""")
