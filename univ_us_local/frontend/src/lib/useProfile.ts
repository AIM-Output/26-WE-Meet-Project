"use client";

import { useStored } from "./storage";
import { demoDepartments, emptyProfile, isProfileComplete, type Profile } from "./demo";

// C2 프로필 — GET/PUT /api/profile 이 생기기 전까지 브라우저에 둔다.
export function useProfile() {
  const [profile, setProfile] = useStored<Profile>("profile", emptyProfile);
  const dept = demoDepartments.find((d) => d.code === profile.deptCode) ?? null;
  return { profile, setProfile, dept, complete: isProfileComplete(profile) };
}
