"""NutriSnap - dish photo nutrition check + personalised diet plan with recipes.
Run: streamlit run app.py   (needs ANTHROPIC_API_KEY in Streamlit secrets)
Estimates only; not medical advice."""
import base64, io, json, re
from datetime import date
import anthropic
import pandas as pd
import streamlit as st
from PIL import Image

MODEL = "claude-sonnet-5-5"
st.session_state.setdefault("log", [])
st.session_state.setdefault("weights", [])
st.set_page_config(page_title="NutriSnap", page_icon="🥗", layout="centered")
st.title("🥗 NutriSnap")
st.caption("Estimates from AI and standard formulas. Not medical advice.")

try:
    client = anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])
except Exception:
    st.error("Add ANTHROPIC_API_KEY in the app's Secrets (see README)."); st.stop()


def ask(content, system, max_tokens=1500) -> str:
    r = client.messages.create(model=MODEL, max_tokens=max_tokens, system=system,
                               messages=[{"role": "user", "content": content}])
    return "".join(b.text for b in r.content if b.type == "text")


def to_b64(file) -> str:
    img = Image.open(file).convert("RGB")
    img.thumbnail((1024, 1024))
    buf = io.BytesIO(); img.save(buf, "JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode()


def parse_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    return json.loads(m.group(0))


DISH_SYSTEM = """You are a nutrition analyst. Look at the food photo and estimate nutrition for the
portion shown. Reply with ONLY JSON, no markdown:
{"is_food": true, "dish": str, "portion": str, "calories": num, "protein_g": num, "carbs_g": num,
 "fat_g": num, "fibre_g": num,
 "vitamins": [{"name": str, "amount": str, "pct_daily_value": num}],
 "minerals": [{"name": str, "amount": str, "pct_daily_value": num}],
 "protein_quality": str, "tips": [str], "confidence": "low|medium|high"}
Include 5-8 key vitamins (A, C, D, E, K, B1, B2, B3, B6, B9, B12 as relevant). Use adult daily values.
If the image is not food, return {"is_food": false}."""

tab1, tab2, tab3 = st.tabs(["📷 Analyze a dish", "📋 Diet plan & recipes", "📒 Daily log & progress"])

with tab1:
    src = st.radio("Photo source", ["Upload", "Camera"], horizontal=True)
    photo = st.file_uploader("Dish photo", type=["jpg", "jpeg", "png", "webp"]) if src == "Upload" \
        else st.camera_input("Take a photo")
    note = st.text_input("Optional note (e.g. '2 rotis, 1 bowl dal', 'cooked in ghee')")
    if photo:
        st.image(photo, use_container_width=True)
        if st.button("Analyze nutrition", type="primary"):
            with st.spinner("Analyzing your dish..."):
                try:
                    content = [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                            "data": to_b64(photo)}},
                               {"type": "text", "text": f"Analyze this dish. User note: {note or 'none'}"}]
                    d = parse_json(ask(content, DISH_SYSTEM))
                    st.session_state.dish = d
                except Exception as e:
                    st.error(f"Could not analyze the photo: {e}")
    d = st.session_state.get("dish")
    if d:
        if not d.get("is_food"):
            st.warning("This doesn't look like food. Try another photo.")
        else:
            st.subheader(f"{d['dish']}  ·  {d['portion']}")
            c = st.columns(4)
            c[0].metric("Calories", f"{d['calories']:.0f}")
            c[1].metric("Protein", f"{d['protein_g']:.0f} g")
            c[2].metric("Carbs", f"{d['carbs_g']:.0f} g")
            c[3].metric("Fat", f"{d['fat_g']:.0f} g")
            st.write(f"**Protein quality:** {d['protein_quality']}  ·  **Fibre:** {d['fibre_g']:.0f} g")
            rows = d.get("vitamins", []) + d.get("minerals", [])
            if rows:
                df = pd.DataFrame(rows)
                st.bar_chart(df.set_index("name")["pct_daily_value"])
                st.dataframe(df.rename(columns={"name": "Nutrient", "amount": "Amount",
                                                "pct_daily_value": "% Daily Value"}),
                             hide_index=True, use_container_width=True)
            for t in d.get("tips", []): st.write("•", t)
            st.caption(f"Confidence: {d.get('confidence', 'medium')}. Portion size is the biggest source of error.")
            if st.button("➕ Add to today's log"):
                st.session_state.log.append({"date": str(date.today()), "meal": "Meal", "dish": d["dish"],
                                             "calories": round(d["calories"]), "protein_g": round(d["protein_g"])})
                st.success("Added. See the Daily log tab.")

with tab2:
    st.subheader("Your details")
    c1, c2, c3 = st.columns(3)
    age = c1.number_input("Age", 16, 90, 22)
    sex = c2.selectbox("Sex", ["Male", "Female"])
    act = c3.selectbox("Activity", ["Sedentary", "Light", "Moderate", "Very active"], index=1)
    c1, c2 = st.columns(2)
    ht = c1.number_input("Height (cm)", 120, 220, 170)
    wt = c2.number_input("Weight (kg)", 30.0, 200.0, 65.0)
    goal = st.selectbox("Goal", ["Lose fat", "Maintain weight", "Build muscle"])
    diet = st.selectbox("Diet type", ["Vegetarian", "Eggetarian", "Non-vegetarian", "Vegan"])
    cuisine = st.text_input("Preferred cuisine", "South Indian / Indian")
    avoid = st.text_input("Allergies or foods to avoid", "")
    days = st.slider("Days in plan", 1, 3, 1)
    budget = st.selectbox("Cooking effort", ["Quick (under 20 min)", "Normal", "I enjoy cooking"], index=1)

    bmr = 10 * wt + 6.25 * ht - 5 * age + (5 if sex == "Male" else -161)
    tdee = bmr * {"Sedentary": 1.2, "Light": 1.375, "Moderate": 1.55, "Very active": 1.725}[act]
    target = tdee + {"Lose fat": -400, "Maintain weight": 0, "Build muscle": 300}[goal]
    floor = 1500 if sex == "Male" else 1200
    target = max(target, floor)
    prot = wt * {"Lose fat": 1.6, "Maintain weight": 1.2, "Build muscle": 1.8}[goal]
    st.session_state.targets = (target, prot)
    m = st.columns(3)
    m[0].metric("Daily calories", f"{target:.0f}")
    m[1].metric("Protein target", f"{prot:.0f} g")
    m[2].metric("BMR", f"{bmr:.0f}")
    st.caption("Mifflin-St Jeor formula, with a safe calorie floor. Check with a doctor or dietitian "
               "if you have a medical condition, are pregnant, or are under 18.")

    if st.button("Create my diet plan", type="primary"):
        prompt = f"""Create a {days}-day {diet} meal plan with recipes.
Daily targets: about {target:.0f} kcal and at least {prot:.0f} g protein. Goal: {goal}.
Cuisine: {cuisine}. Avoid: {avoid or 'nothing'}. Cooking effort: {budget}. Person: {age}y {sex}, {wt}kg.
Use affordable, easy-to-find ingredients. For each day give breakfast, lunch, snack, dinner with
approx kcal and protein for each, a day total, and key vitamins covered. Then give a full recipe
(ingredients with quantities, steps, time) for every dish. End with a short grocery list and 3 tips
to stay consistent. Use clear markdown headings."""
        with st.spinner("Building your plan and recipes..."):
            try:
                st.session_state.plan = ask(prompt, "You are a registered-dietitian style assistant. "
                                            "Be practical and precise. Never recommend crash diets.", 4000)
            except Exception as e:
                st.error(f"Could not create the plan: {e}")
    if st.session_state.get("plan"):
        st.markdown(st.session_state.plan)
        st.download_button("Download plan", st.session_state.plan, "diet_plan.md")


with tab3:
    tcal, tprot = st.session_state.get("targets", (2000, 60))
    if "targets" not in st.session_state:
        st.info("Using default targets (2000 kcal, 60 g protein). Set yours in the Diet plan tab.")
    day = st.date_input("Date", date.today())

    st.subheader("Food log")
    c = st.columns([1.2, 2, 1, 1])
    meal = c[0].selectbox("Meal", ["Breakfast", "Lunch", "Snack", "Dinner"])
    name = c[1].text_input("Dish")
    kcal = c[2].number_input("kcal", 0, 3000, 0)
    pro = c[3].number_input("Protein g", 0, 200, 0)
    b = st.columns(2)
    if b[0].button("Add entry") and name:
        st.session_state.log.append({"date": str(day), "meal": meal, "dish": name,
                                     "calories": kcal, "protein_g": pro}); st.rerun()
    if b[1].button("Remove last entry for this day"):
        idx = [i for i, e in enumerate(st.session_state.log) if e["date"] == str(day)]
        if idx: st.session_state.log.pop(idx[-1]); st.rerun()

    df = pd.DataFrame(st.session_state.log, columns=["date", "meal", "dish", "calories", "protein_g"])
    today = df[df.date == str(day)]
    st.dataframe(today.drop(columns="date"), hide_index=True, use_container_width=True)
    cal, protein = today.calories.sum(), today.protein_g.sum()
    st.write(f"**Calories:** {cal:.0f} / {tcal:.0f}")
    st.progress(min(cal / tcal, 1.0))
    st.write(f"**Protein:** {protein:.0f} g / {tprot:.0f} g")
    st.progress(min(protein / tprot, 1.0))
    if len(today):
        left = tprot - protein
        st.caption(f"{left:.0f} g protein left to reach your goal." if left > 0 else "Protein goal reached.")

    st.subheader("Weekly progress")
    w1, w2 = st.columns([2, 1])
    wnew = w1.number_input("Today's weight (kg)", 30.0, 200.0, 65.0, step=0.1)
    if w2.button("Log weight"):
        st.session_state.weights = [x for x in st.session_state.weights if x["date"] != str(day)]
        st.session_state.weights.append({"date": str(day), "weight": wnew}); st.rerun()
    if st.session_state.weights:
        wd = pd.DataFrame(st.session_state.weights).sort_values("date")
        wd["date"] = pd.to_datetime(wd["date"])
        st.line_chart(wd.set_index("date")["weight"])
        wk = wd.groupby(wd.date.dt.to_period("W").dt.start_time)["weight"].mean().round(1).to_frame("Avg weight (kg)")
        wk["Change vs last week"] = wk["Avg weight (kg)"].diff().round(1)
        wk.index = wk.index.strftime("Week of %d %b")
        st.dataframe(wk, use_container_width=True)
    if len(df):
        dd = df.copy(); dd["date"] = pd.to_datetime(dd["date"])
        daily = dd.groupby("date")[["calories", "protein_g"]].sum().tail(7)
        st.write(f"**Last {len(daily)} logged days, average:** {daily.calories.mean():.0f} kcal, "
                 f"{daily.protein_g.mean():.0f} g protein per day")
        st.bar_chart(daily)

    st.subheader("Save / restore")
    st.caption("The app forgets data when the page reloads. Download your data and restore it next time.")
    st.download_button("Download my data", json.dumps({"log": st.session_state.log,
                       "weights": st.session_state.weights}), "nutrisnap_data.json")
    up = st.file_uploader("Restore data file", type=["json"])
    if up and st.button("Restore"):
        try:
            data = json.load(up)
            st.session_state.log, st.session_state.weights = data["log"], data["weights"]; st.rerun()
        except Exception:
            st.error("That file isn't a valid NutriSnap data file.")
