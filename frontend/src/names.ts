import type { Answers } from "./api";

// Names and descriptions a farmer would use. The data keeps the research wording.
const PLAIN_NAME: Record<string, string> = {
  reduced_tillage: "Reduced tillage (plough less)",
  no_till: "No-till (no ploughing at all)",
  shift_up_throttle_down: "Change up a gear and ease the throttle back",
  hvo_switch: "Switch to HVO (a cleaner diesel)",
  correct_tyre_pressure: "Set the right tyre pressure",
  central_tyre_inflation: "Central tyre inflation (change pressure from the cab)",
  avoid_liquid_ballast: "Stop using liquid weights in the tyres",
  electric_tractor: "Electric tractor (small)",
};
export const plain = (i: { intervention_id: string; name: string }) => PLAIN_NAME[i.intervention_id] ?? i.name;

// One line for the collapsed card, a few sentences for the expanded one.
export const IDEA: Record<string, { summary: string; detail: string; action: string }> = {
  reduced_tillage: {
    summary: "Work the soil less. Use a lighter cultivator instead of the plough.",
    detail:
      "You turn the soil less deeply and less often, so the tractor uses less diesel on every hectare. You still prepare a seedbed. It is a smaller change than no-till.",
    action:
      "Pick fields where a lighter cultivator could replace the plough, and agree it with the client farm. Try a few fields first and compare litres per hectare.",
  },
  no_till: {
    summary: "Do not plough at all. Sow straight into the stubble.",
    detail:
      "A direct drill sows into last year's stubble with no ploughing or cultivating first. It saves the most fuel of the soil ideas, but it changes how you grow your crop, so think it through first.",
    action:
      "Needs a direct drill and the client farm's agreement. Trial it on a few fields before offering it widely.",
  },
  shift_up_throttle_down: {
    summary: "On light jobs, change up a gear and lower the engine speed.",
    detail:
      "The tractor does the same work at a lower engine speed, so it burns less diesel. It suits jobs where you pull something along, not jobs that run off the power take-off.",
    action:
      "Ask drivers to try it on towed jobs such as ploughing. Pilot it on one tractor and watch litres per hour on the same job.",
  },
  hvo_switch: {
    summary: "Use HVO, a diesel made from waste oils, instead of red diesel.",
    detail:
      "HVO releases far less CO2 than red diesel. You burn a little more of it, and it costs more per litre, so your fuel bill goes up while your emissions come down.",
    action:
      "Ask a fuel supplier for an HVO quote and compare the extra cost with the emissions avoided. Check each tractor's manual first.",
  },
  correct_tyre_pressure: {
    summary: "Set tyre pressure to the maker's table for your load.",
    detail: "Tyres that are too hard slip in the field and waste fuel. Tyres set to the table grip better and use less diesel.",
    action:
      "Check each tractor's tyre pressures against the maker's table, then answer the question on this card.",
  },
  central_tyre_inflation: {
    summary: "Fit a system that changes tyre pressure from the cab.",
    detail:
      "You can run low pressure in the field and higher pressure on the road without stopping. The kit is fitted to an existing tractor.",
    action:
      "Find out whether any tractor already has one, then answer the question on this card. Fitting is a one-off cost per tractor.",
  },
  avoid_liquid_ballast: {
    summary: "Take liquid weight out of the tyres if you do not need it.",
    detail:
      "Extra weight makes the tractor burn more fuel. Liquid weight inside the tyres can raise fuel use, so removing what you do not need can cut it.",
    action:
      "Check whether any tyres are filled with liquid weight, then answer the question on this card.",
  },
};

// The questions we can ask, the answers a farmer can give, and which idea each one belongs to.
export interface Question {
  question: string;
  hint?: string;
  why: string; // why we ask, in the farmer's terms
  yes: { label: string; value: boolean | string };
  no: { label: string; value: boolean | string };
}

export const QUESTIONS: Record<keyof Answers, Question> = {
  tyre_pressure_checked: {
    question: "Have the tractors' tyre pressures been checked against the maker's table?",
    why: "Tyres that are too hard waste fuel. If they have not been checked, there is fuel to save. If they have, there is little left to gain.",
    yes: { label: "Yes, checked", value: true },
    no: { label: "No, not checked", value: false },
  },
  has_ctis: {
    question: "Does any tractor have a system that changes tyre pressure from the cab?",
    hint: "This is called a central tyre inflation system.",
    why: "If a tractor already changes its tyre pressure from the cab, fitting a system would save nothing new.",
    yes: { label: "Yes, one does", value: true },
    no: { label: "No, none do", value: false },
  },
  ballast_type: {
    question: "Do the tractors have liquid weight (water or fluid) inside the tyres?",
    why: "Liquid weight in the tyres can raise fuel use. If you have none, there is nothing to take out.",
    yes: { label: "Yes, they do", value: "liquid" },
    no: { label: "No, they do not", value: "none" },
  },
};

export const QUESTION_FOR: Record<string, keyof Answers> = {
  correct_tyre_pressure: "tyre_pressure_checked",
  central_tyre_inflation: "has_ctis",
  avoid_liquid_ballast: "ballast_type",
};
