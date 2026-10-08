"use client";

import { useEffect, useState } from "react";
import { Eye, EyeOff, KeyRound } from "lucide-react";
import { Modal } from "@/components/ui/Modal";
import { Banner } from "@/components/ui/Feedback";
import { useToast } from "@/components/ui/Toast";
import { api } from "@/lib/api";
import type { LoginCreds } from "@/lib/assignments";
import { closeQuery, navigateQuery, useQueryValue } from "@/lib/useQueryState";

// /settings/sources › e클래스 › 학교 로그인 — 자동 로그인 정보(C3 자격증명) 저장·지우기. 모달은 ?creds=1 (push).
// 비밀번호는 PUT 으로 보내기만 하고, 서버는 돌려주지 않는다(C3_Login_agent/login/api.py). 칸은 모달이 닫히면 사라진다.

const KEY = "creds";

export function LoginCredsButton({ saved, onChanged }: { saved: boolean; onChanged: () => void }) {
  const open = useQueryValue(KEY) === "1";
  return (
    <>
      <button type="button" className="btn btn-sm" onClick={() => navigateQuery({ [KEY]: "1" }, "push")}>
        <KeyRound aria-hidden />
        {saved ? "자동 로그인 정보 바꾸기" : "자동 로그인 정보 저장"}
      </button>
      <Modal open={open} onClose={() => closeQuery([KEY])} title="자동 로그인 정보">
        {open && <CredsForm onChanged={onChanged} />}
      </Modal>
    </>
  );
}

function CredsForm({ onChanged }: { onChanged: () => void }) {
  const toast = useToast();
  const [info, setInfo] = useState<LoginCreds | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let alive = true;
    api
      .loginCreds()
      .then((c) => {
        if (!alive) return;
        setInfo(c);
        setUsername(c.username ?? "");
      })
      .catch((e) => alive && setLoadError(e instanceof Error ? e.message : String(e)));
    return () => {
      alive = false;
    };
  }, []);

  const id = username.trim();
  const valid = id.length > 0 && !/\s/.test(id) && password.length > 0;

  const done = (msg: string) => {
    toast(msg, { tone: "success" });
    onChanged();
    closeQuery([KEY]);
  };
  const save = async () => {
    if (!valid || busy) return;
    setBusy(true);
    try {
      await api.saveLoginCreds({ username: id, password });
      setPassword("");
      done("자동 로그인 정보를 저장했습니다 — 세션이 만료돼도 창 없이 다시 로그인합니다");
    } catch (e) {
      toast(`저장하지 못했습니다: ${e instanceof Error ? e.message : String(e)}`, { tone: "error" });
    } finally {
      setBusy(false);
    }
  };
  const clear = async () => {
    setBusy(true);
    try {
      await api.clearLoginCreds();
      done("자동 로그인 정보를 지웠습니다 — 세션이 만료되면 로그인 창이 필요합니다");
    } catch (e) {
      toast(`지우지 못했습니다: ${e instanceof Error ? e.message : String(e)}`, { tone: "error" });
    } finally {
      setBusy(false);
    }
  };

  const where = info?.store === "keychain" ? "맥 로그인 키체인" : "이 Windows 계정으로만 풀 수 있게 암호화한 파일";
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        void save();
      }}
    >
      <p className="mb-3 text-[13px] text-muted">
        전남대 포털(SSO) 아이디·비밀번호를 이 PC 에만 저장합니다({where}). 학교 세션이 만료되면 창을 띄우지 않고 이 정보로 다시 로그인합니다. 휴대폰 2차
        인증은 &apos;로그인 창 열기&apos;로 한 번 통과해 이 PC 가 신뢰 기기로 등록돼 있어야 생략됩니다.
      </p>
      {loadError && (
        <Banner tone="danger" className="mb-3">
          저장 상태를 불러오지 못했습니다: {loadError}
        </Banner>
      )}
      {info?.saved && !info.username && (
        <Banner tone="warn" className="mb-3">
          저장된 정보를 이 계정에서 풀지 못했습니다 — 다시 저장하세요
        </Banner>
      )}
      <label className="label" htmlFor="creds-user">
        아이디 (학번)
      </label>
      <input
        id="creds-user"
        data-autofocus
        className="field"
        autoComplete="off"
        spellCheck={false}
        value={username}
        onChange={(e) => setUsername(e.target.value)}
      />
      <label className="label mt-3" htmlFor="creds-pw">
        비밀번호
      </label>
      <div className="flex items-center gap-2">
        <input
          id="creds-pw"
          className="field flex-1"
          type={show ? "text" : "password"}
          autoComplete="off"
          spellCheck={false}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder={info?.saved ? "바꾸려면 새 비밀번호를 넣으세요" : ""}
        />
        <button type="button" className="btn btn-ghost btn-sm" aria-label={show ? "비밀번호 숨기기" : "비밀번호 보기"} aria-pressed={show} onClick={() => setShow((v) => !v)}>
          {show ? <EyeOff aria-hidden /> : <Eye aria-hidden />}
        </button>
      </div>
      <p className="hint">비밀번호는 화면·로그에 다시 나오지 않습니다. 학교 비밀번호를 바꾸면 여기서도 바꿔 주세요.</p>
      <div className="mt-5 flex flex-wrap items-center justify-end gap-2">
        {info?.saved && (
          <button type="button" className="btn btn-ghost btn-danger mr-auto" disabled={busy} onClick={() => void clear()}>
            지우기
          </button>
        )}
        <button type="button" className="btn" onClick={() => closeQuery([KEY])}>
          취소
        </button>
        <button type="submit" className="btn btn-primary" disabled={!valid || busy}>
          {busy && <span className="spin" aria-hidden />}
          저장
        </button>
      </div>
    </form>
  );
}
