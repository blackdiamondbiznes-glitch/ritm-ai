/** The active business vertical. Only tutors exist today; the shell reads this pack. */
export const tutor = {
  id: "tutor",
  home: { teacher: "cabinet", student: "study" },
  terms: {
    group: "grpName",
    lesson: "lesTitle",
    student: "stuName",
    attendance: "attNav",
    homework: "hwTitle",
    fee: "feeNav",
  },
  teacherTabs: ["cabinet"],
  teacherCommunityTabs: ["chats"],
  studentTabs: ["study"],
  studentCommunityTabs: ["board", "history"],
};

/** Niche selects the pack later. Until then every cabinet is the tutor vertical. */
export function currentVertical() {
  return tutor;
}
