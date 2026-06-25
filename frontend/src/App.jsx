import { useEffect, useMemo, useState } from "react";
import { Menu, PanelLeftClose } from "lucide-react";
import {
  askChat,
  createProject,
  fetchLawDetail,
  generateChecklist as generateChecklistFromApi,
  listChatHistory,
  listChecklistHistory,
  listExportHistory,
  listProjects,
  saveChatHistory,
  saveChecklistHistory,
  saveExportHistory,
} from "./api";

const defaultProjects = [
  { id: "p1", name: "진주 지식산업센터 신축 현장", updatedAt: "2026-04-13" },
  { id: "p2", name: "건설공사 현장", updatedAt: "2026-04-12" },
];

const workTypeOptions = ["고소작업", "전기작업", "밀폐공간", "굴착", "용접", "중장비", "철골 조립", "해체공사"];
const environmentOptions = ["실내", "실외", "고소", "야간", "폭염", "한랭", "밀폐", "복합 작업"];
const riskFactorOptions = ["추락", "낙하물", "감전", "화재", "끼임", "중량물", "분진", "유해가스"];
const safetyItems = [
  "작업 전 TBM 실시",
  "사전 위험성평가 실시",
  "보호구 지급 및 착용 확인",
  "안전난간 또는 추락방지 조치",
  "전원 차단 및 잠금표시",
  "밀폐공간 산소·유해가스 측정",
];

const uuidPattern = /\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b:?\s*/g;

function riskLabel(risk) {
  if (risk === "high") return { text: "고위험", className: "badge danger" };
  if (risk === "mid") return { text: "중위험", className: "badge warning" };
  return { text: "저위험", className: "badge success" };
}

function readinessBadgeClass(value) {
  if (value === "READY" || value === "ALLOW_DIRECT_ANSWER" || value === "success") return "badge success";
  if (value === "NOT_READY" || value === "REFUSE_OR_REQUEST_MORE_EVIDENCE" || value === "danger" || value === "high") {
    return "badge danger";
  }
  if (
    value === "INDIRECT_ONLY" ||
    value === "INDIRECT_ONLY_RESPONSE" ||
    value === "LIMITED_EVIDENCE" ||
    value === "READY_WITH_WARNINGS" ||
    value === "ALLOW_WITH_CAUTION" ||
    value === "warning" ||
    value === "medium"
  ) {
    return "badge warning";
  }
  return "badge info";
}

function badgeLabel(value) {
  const labels = {
    READY: "직접 근거 확인",
    READY_WITH_WARNINGS: "주의 필요",
    INDIRECT_ONLY: "간접 근거만 확인",
    LIMITED_EVIDENCE: "근거 제한",
    NOT_READY: "추가 근거 필요",
    ALLOW_DIRECT_ANSWER: "직접 근거 기반 답변",
    ALLOW_WITH_CAUTION: "조건 확인 필요",
    INDIRECT_ONLY_RESPONSE: "간접 근거 기반 제한 답변",
    REFUSE_OR_REQUEST_MORE_EVIDENCE: "추가 근거 필요",
  };
  return labels[value] || value || "상태 미확인";
}

function answerPolicyInfo(value) {
  const policies = {
    ALLOW_DIRECT_ANSWER: {
      label: "직접 근거 기반 답변",
      description: "현재 연결된 근거를 바탕으로 직접 답변할 수 있습니다.",
      className: "success",
    },
    ALLOW_WITH_CAUTION: {
      label: "조건 확인 필요",
      description: "근거는 확인되었지만 적용 조건, 예외 또는 수치 기준을 함께 검토해야 합니다.",
      className: "warning",
    },
    INDIRECT_ONLY_RESPONSE: {
      label: "간접 근거만 확인",
      description:
        "현재 지식베이스에서는 이 질문에 직접 답할 수 있는 법령 근거가 확인되지 않았습니다. 아래 답변은 관련 간접 근거를 바탕으로 한 제한적 설명입니다.",
      className: "warning",
    },
    REFUSE_OR_REQUEST_MORE_EVIDENCE: {
      label: "추가 근거 필요",
      description: "현재 근거만으로는 답변을 단정하기 어렵습니다. 추가 조건이나 직접 근거가 필요합니다.",
      className: "danger",
    },
  };
  return policies[value] || { label: badgeLabel(value), description: "답변 근거 상태를 확인하세요.", className: "info" };
}

function stripInternalIds(value) {
  return String(value || "")
    .replace(uuidPattern, "")
    .replace(/warning:\s*[A-Z_]+\s*-\s*/gi, "")
    .replace(/\b(?:source_node_id|source_anchor_id|rule_id|list_item_id)\s*[:=]\s*\S+/gi, "")
    .trim();
}

function normalizeLegalText(value) {
  const text = stripInternalIds(value)
    .replace(/\r\n/g, "\n")
    .replace(/[ \t]+/g, " ")
    .replace(/\n{3,}/g, "\n\n")
    .trim();

  if (!text) return "";

  return text
    .replace(/\s+(?=제\s*\d+\s*조(?:의\s*\d+)?)/g, "\n\n")
    .replace(/\s+(?=[①②③④⑤⑥⑦⑧⑨⑩])/g, "\n")
    .replace(/\s+(?=\d+\.\s)/g, "\n")
    .replace(/\s+(?=[가-하]\.\s)/g, "\n")
    .replace(/\s+(?=다만[,，])/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function previewText(value, maxLength = 250) {
  const text = normalizeLegalText(value).replace(/\s+/g, " ").trim();
  if (!text) return "";
  return text.length > maxLength ? `${text.slice(0, maxLength - 3).trim()}...` : text;
}

function legalPreview(value, maxLength = 1200) {
  const text = normalizeLegalText(value);
  if (!text) return "";
  return text.length > maxLength ? `${text.slice(0, maxLength).trim()}...` : text;
}

function cleanAnswerText(value) {
  return normalizeLegalText(value)
    .replace(/^-?\s*warning:.*$/gim, "")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function splitBulletText(value, maxItems = 8) {
  const text = normalizeLegalText(value);
  if (!text) return [];
  return text
    .split(/\n+/)
    .map((line) => line.replace(/^[-•]\s*/, "").trim())
    .filter(Boolean)
    .slice(0, maxItems);
}

function itemText(item, fallback = "항목") {
  if (typeof item === "string") return stripInternalIds(item);
  if (!item || typeof item !== "object") return fallback;
  return stripInternalIds(
    item.message ||
      item.description ||
      item.label ||
      item.reason ||
      item.warning_type ||
      item.evidence_type ||
      item.title ||
      fallback
  );
}

function userFacingWarning(item) {
  const text = itemText(item, "주의사항");
  if (/THRESHOLD_MISSING/i.test(text)) {
    return "교육시간 등 수치 기준이 구조화된 값으로 분리되지 않았습니다. 정확한 값은 연결된 조문 또는 별표 원문에서 확인해야 합니다.";
  }
  if (/DIRECT_PENALTY_NOT_FOUND/i.test(text)) {
    return "현재 연결된 근거에서는 직접 처벌 조항이 확인되지 않았습니다.";
  }
  if (/CANDIDATE_PENALTY_REQUIRES_REVIEW/i.test(text)) {
    return "관련 가능성이 있는 벌칙·과태료 조항 후보가 있으나 확정 결론은 아닙니다.";
  }
  return text || "적용 조건 또는 예외 확인이 필요합니다.";
}

function dedupeByMessage(items = []) {
  const seen = new Set();
  return items.filter((item) => {
    const text = userFacingWarning(item);
    if (seen.has(text)) return false;
    seen.add(text);
    return true;
  });
}

function parseAnswerSections(value) {
  const clean = cleanAnswerText(value);
  if (!clean) return [];
  const pattern = /\[(결론|근거|주의|다음 확인|참고)\]\s*/g;
  const matches = [...clean.matchAll(pattern)];
  if (!matches.length) return [{ title: "답변", body: clean }];

  return matches
    .map((match, index) => {
      const start = match.index + match[0].length;
      const end = matches[index + 1]?.index ?? clean.length;
      return { title: match[1], body: clean.slice(start, end).trim() };
    })
    .filter((section) => section.body);
}

function isWeakSummary(summary, text) {
  const s = normalizeLegalText(summary);
  const t = normalizeLegalText(text);
  if (!s) return true;
  if (s.length < 18) return true;
  if (t && t.includes(s)) return true;
  if (s.includes("해당 근거는") && s.includes("법령 근거")) return true;
  if (s.includes("체크리스트 항목") && s.includes("확인")) return true;
  return false;
}

function hasDirectPenalty(item) {
  return Array.isArray(item?.penalties) && item.penalties.length > 0;
}

function hasCandidatePenalty(item) {
  return Array.isArray(item?.candidate_penalties) && item.candidate_penalties.length > 0;
}

function hasLinkedEvidence(item) {
  return Boolean(item?.node_id || item?.law_node_id || item?.evidences?.length);
}

function needsSecondaryReview(item) {
  return Boolean(
    item?.answer_policy === "ALLOW_WITH_CAUTION" ||
      item?.evidence_readiness === "READY_WITH_WARNINGS" ||
      item?.evidence_readiness === "LIMITED_EVIDENCE" ||
      item?.evidence_readiness === "INDIRECT_ONLY" ||
      item?.warnings?.length ||
      item?.penalty_warnings?.length
  );
}

function chipNodeId(chip) {
  return chip?.source_node_id || chip?.source_anchor_id || chip?.rule_id || chip?.list_item_id || chip?.node_id || null;
}

function chipLabel(chip) {
  return (
    stripInternalIds(chip?.label || chip?.citation_text) ||
    [chip?.law_name, chip?.article_no, chip?.annex_title].filter(Boolean).join(" ") ||
    chip?.title ||
    "근거"
  );
}

function fallbackEvidenceChips(message) {
  if (Array.isArray(message?.evidence_chips) && message.evidence_chips.length) return message.evidence_chips;
  if (Array.isArray(message?.citations) && message.citations.length) {
    return message.citations.map((citation, idx) => ({
      id: `citation-${idx}`,
      label: citation.citation_text || [citation.law_name, citation.article_no].filter(Boolean).join(" "),
      type: citation.evidence_kind || "근거",
      preview: citation.source_text_preview || citation.preview || "",
      source_node_id: citation.source_node_id,
      source_anchor_id: citation.source_anchor_id,
      node_id: citation.node_id,
      law_name: citation.law_name,
      article_no: citation.article_no,
      annex_title: citation.annex_title,
    }));
  }
  if (Array.isArray(message?.evidences) && message.evidences.length) {
    return message.evidences.map((evidence, idx) => ({
      id: `evidence-${idx}`,
      label: evidence.title || evidence.law_name || evidence.type,
      type: evidence.type || "근거",
      preview: evidence.source_text || evidence.preview || "",
      node_id: evidence.node_id,
      law_name: evidence.law_name,
    }));
  }
  return [];
}

function qualityVerdict(message) {
  if (message?.answer_policy === "ALLOW_DIRECT_ANSWER") {
    return {
      label: "직접 답변 가능",
      className: "success",
      description: "직접 연결된 근거를 바탕으로 답변할 수 있는 상태입니다.",
      nextAction: "근거 원문을 확인하고 현장 조건과 일치하는지 검토하세요.",
    };
  }
  if (message?.answer_policy === "ALLOW_WITH_CAUTION") {
    return {
      label: "조건 확인 필요",
      className: "warning",
      description: "근거는 확인되었지만 적용 조건, 예외 또는 수치 기준 확인이 필요합니다.",
      nextAction: "대상, 작업유형, 교육구분, 예외 조건을 추가로 확인하세요.",
    };
  }
  if (message?.answer_policy === "INDIRECT_ONLY_RESPONSE") {
    return {
      label: "직접 단정 불가",
      className: "warning",
      description: "직접 근거가 아니라 간접 근거만 확인된 답변입니다.",
      nextAction: "직접 의무 조항이 있는지 별도 확인하기 전에는 단정하지 마세요.",
    };
  }
  return {
    label: "추가 근거 필요",
    className: "danger",
    description: "현재 근거만으로는 답변 품질을 보장하기 어렵습니다.",
    nextAction: "질문 조건을 구체화하거나 직접 근거를 추가로 확인하세요.",
  };
}

function toggleValue(list, value) {
  return list.includes(value) ? list.filter((item) => item !== value) : [...list, value];
}

function saveQuietly(promise) {
  promise?.catch(() => undefined);
}

export default function App() {
  const [page, setPage] = useState("checklist");
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [projects, setProjects] = useState(defaultProjects);
  const [selectedProjectId, setSelectedProjectId] = useState(defaultProjects[0].id);
  const [siteName, setSiteName] = useState("진주 지식산업센터 신축 현장");
  const [industry, setIndustry] = useState("건설업");
  const [workerCount, setWorkerCount] = useState(12);
  const [workTypes, setWorkTypes] = useState(["고소작업"]);
  const [environments, setEnvironments] = useState(["실외"]);
  const [hazards, setHazards] = useState(["추락", "낙하물"]);
  const [specialNotes, setSpecialNotes] = useState("");
  const [safetyState, setSafetyState] = useState(() =>
    Object.fromEntries(safetyItems.map((item, index) => [item, index < 2]))
  );

  const [checklistItems, setChecklistItems] = useState([]);
  const [checklistFilter, setChecklistFilter] = useState("all");
  const [checklistLoading, setChecklistLoading] = useState(false);

  const [chatMessages, setChatMessages] = useState([]);
  const [qaInput, setQaInput] = useState("");
  const [chatSending, setChatSending] = useState(false);

  const [selectedLaw, setSelectedLaw] = useState(null);
  const [lawLoading, setLawLoading] = useState(false);
  const [lawError, setLawError] = useState("");

  const [exploreQuery, setExploreQuery] = useState("");
  const [exploreNodeId, setExploreNodeId] = useState("");
  const [historyRows, setHistoryRows] = useState({ checklists: [], chats: [], exports: [] });

  const selectedProject = projects.find((project) => project.id === selectedProjectId) || projects[0];

  const refreshHistory = async () => {
    const [checklists, chats, exports] = await Promise.allSettled([
      listChecklistHistory(),
      listChatHistory(),
      listExportHistory(),
    ]);
    setHistoryRows({
      checklists: checklists.status === "fulfilled" ? checklists.value || [] : [],
      chats: chats.status === "fulfilled" ? chats.value || [] : [],
      exports: exports.status === "fulfilled" ? exports.value || [] : [],
    });
  };

  useEffect(() => {
    listProjects()
      .then((rows) => {
        if (Array.isArray(rows) && rows.length) setProjects(rows);
      })
      .catch(() => undefined);
    refreshHistory().catch(() => undefined);
  }, []);

  const filteredChecklist = useMemo(() => {
    if (checklistFilter === "high") return checklistItems.filter((item) => item.risk === "high");
    if (checklistFilter === "unchecked") return checklistItems.filter((item) => !item.completed);
    if (checklistFilter === "evidence_linked") return checklistItems.filter((item) => hasLinkedEvidence(item));
    if (checklistFilter === "candidate_penalty") return checklistItems.filter((item) => hasCandidatePenalty(item));
    if (checklistFilter === "direct_penalty") return checklistItems.filter((item) => hasDirectPenalty(item));
    if (checklistFilter === "needs_review") return checklistItems.filter((item) => needsSecondaryReview(item));
    return checklistItems;
  }, [checklistFilter, checklistItems]);

  const qaMessages = chatMessages.filter((message) => message.role === "user" || message.role === "assistant");
  const assistantMessages = chatMessages.filter((message) => message.role === "assistant" && !message.error);

  const evidenceGroups = useMemo(() => {
    const groups = [];

    chatMessages.forEach((message, idx) => {
      if (message.role !== "assistant" || message.error) return;
      const previousUser = [...chatMessages.slice(0, idx)].reverse().find((row) => row.role === "user");
      const chips = fallbackEvidenceChips(message);
      if (!chips.length) return;
      groups.push({
        id: `qa-group-${idx}`,
        groupType: "qa",
        title: previousUser?.text || "질문 정보 없음",
        subtitle: "QA 답변에 사용된 근거",
        answerPreview: previewText(cleanAnswerText(message.text), 180),
        answer_policy: message.answer_policy,
        evidence_readiness: message.evidence_readiness,
        items: chips.map((chip, chipIdx) => ({
          id: chipNodeId(chip) || chip.id || `qa-${idx}-${chipIdx}`,
          label: chipLabel(chip),
          type: chip.type || chip.evidence_kind || "근거",
          preview: stripInternalIds(chip.preview || chip.source_text_preview || ""),
          node_id: chipNodeId(chip),
        })),
      });
    });

    checklistItems.forEach((item, idx) => {
      const items = (item.evidences || []).map((evidence, evidenceIdx) => ({
        id: evidence.node_id || `${item.id}-${evidenceIdx}`,
        label: evidence.title || evidence.law_name || evidence.type || "근거",
        type: evidence.type || "체크리스트 근거",
        preview: stripInternalIds(evidence.source_text || evidence.preview || ""),
        node_id: evidence.node_id,
      }));

      if (item.node_id || item.law_node_id) {
        items.unshift({
          id: item.node_id || item.law_node_id,
          label: item.law_title || item.title || item.text || "대표 연결 근거",
          type: "대표 연결 근거",
          preview: item.description || item.text || "",
          node_id: item.node_id || item.law_node_id,
        });
      }

      if (!items.length) return;
      groups.push({
        id: `checklist-group-${item.id || idx}`,
        groupType: "checklist",
        title: item.title || item.text || "체크리스트 항목",
        subtitle: "체크리스트 항목에 연결된 근거",
        answerPreview: item.description || item.law_title || "",
        answer_policy: item.answer_policy,
        evidence_readiness: item.evidence_readiness,
        candidatePenaltyCount: item.candidate_penalties?.length || 0,
        directPenaltyCount: item.penalties?.length || 0,
        items,
      });
    });

    const query = exploreQuery.trim().toLowerCase();
    if (!query) return groups;
    return groups.filter((group) => {
      const haystack = [
        group.title,
        group.subtitle,
        group.answerPreview,
        group.answer_policy,
        group.evidence_readiness,
        ...group.items.map((item) => `${item.label} ${item.type} ${item.preview}`),
      ]
        .join(" ")
        .toLowerCase();
      return haystack.includes(query);
    });
  }, [chatMessages, checklistItems, exploreQuery]);

  const validationStats = useMemo(() => {
    const answerMessages = assistantMessages.filter((message) => message.answer_policy || message.evidence_readiness);
    return {
      answerMessages,
      direct: answerMessages.filter((message) => message.answer_policy === "ALLOW_DIRECT_ANSWER").length,
      caution: answerMessages.filter((message) => message.answer_policy === "ALLOW_WITH_CAUTION").length,
      indirect: answerMessages.filter((message) => message.answer_policy === "INDIRECT_ONLY_RESPONSE").length,
      needEvidence: answerMessages.filter((message) => message.answer_policy === "REFUSE_OR_REQUEST_MORE_EVIDENCE").length,
    };
  }, [assistantMessages]);

  const complianceRate = checklistItems.length
    ? Math.round((checklistItems.filter((item) => item.completed).length / checklistItems.length) * 100)
    : 0;

  const generateChecklist = async () => {
    setChecklistLoading(true);
    try {
      const payload = {
        site_name: siteName,
        industry,
        work_types: workTypes,
        environments,
        hazards,
        equipment: [],
        worker_count: Number(workerCount) || 0,
        subcontract: null,
        safety_state: safetyState,
        special_notes: specialNotes,
      };
      const result = await generateChecklistFromApi(payload);
      const items = (result.items || []).map((item, idx) => ({
        ...item,
        id: item.id || `item-${Date.now()}-${idx}`,
        completed: Boolean(item.completed),
      }));
      setChecklistItems(items);
      saveQuietly(
        saveChecklistHistory({
          project_id: selectedProjectId,
          site_name: siteName,
          items,
          answer: result.answer,
        }).then(refreshHistory)
      );
    } catch (error) {
      window.alert(error.message || "체크리스트 생성에 실패했습니다.");
    } finally {
      setChecklistLoading(false);
    }
  };

  const addCustomItem = () => {
    const text = window.prompt("추가할 체크리스트 항목을 입력하세요.");
    if (!text?.trim()) return;
    setChecklistItems((prev) => [
      ...prev,
      {
        id: `custom-${Date.now()}`,
        title: text.trim(),
        text: text.trim(),
        risk: "mid",
        law_title: "직접 추가 항목",
        autoCheck: false,
        completed: false,
        custom: true,
        evidences: [],
        penalties: [],
        candidate_penalties: [],
      },
    ]);
  };

  const openLaw = async (itemOrNodeId) => {
    const nodeId =
      typeof itemOrNodeId === "object"
        ? itemOrNodeId?.node_id || itemOrNodeId?.law_node_id
        : itemOrNodeId;
    const fallbackTitle =
      typeof itemOrNodeId === "object"
        ? itemOrNodeId?.law_title || itemOrNodeId?.title || itemOrNodeId?.text
        : itemOrNodeId;

    if (!nodeId) {
      setSelectedLaw({
        title: fallbackTitle || "연결 근거 없음",
        subtitle: "",
        text: "이 항목에는 상세 조회에 사용할 근거 ID가 연결되어 있지 않습니다.",
        formattedText: "이 항목에는 상세 조회에 사용할 근거 ID가 연결되어 있지 않습니다.",
        fullText: "",
        summary: "",
        why: "",
        related: "체크리스트 생성 근거가 연결되면 이곳에서 상세 원문을 확인할 수 있습니다.",
        requirements: "현재 연결된 근거에서 별도 요구사항 구조는 확인되지 않았습니다.",
        requirementItems: [],
        penalty: "",
        penalties: [],
        candidatePenalties: [],
        citations: [],
        warnings: [],
        nodeId: null,
      });
      return;
    }

    setLawLoading(true);
    setLawError("");
    try {
      const detail = await fetchLawDetail(nodeId);
      const citations = detail.citations || [];
      const relatedText =
        citations
          .map((citation) => citation.citation_text || [citation.law_name, citation.article_no].filter(Boolean).join(" "))
          .filter(Boolean)
          .slice(0, 5)
          .join("\n") ||
        (detail.related_sources || [])
          .map((source) => source.citation_text || source.title || source.law_name)
          .filter(Boolean)
          .slice(0, 5)
          .join("\n") ||
        [detail.law_name, detail.article_no, detail.title].filter(Boolean).join(" ") ||
        "관련 근거 출처가 별도로 제공되지 않았습니다.";

      const sourceText = detail.source_text || detail.preview || detail.text || detail.article_text || "법령 본문이 비어 있습니다.";
      const requirementText =
        (detail.requirements || [])
          .map((requirement) => requirement.preview || requirement.text || requirement.title)
          .filter(Boolean)
          .filter((text) => normalizeLegalText(text) !== normalizeLegalText(sourceText))
          .slice(0, 5)
          .join("\n") || "현재 연결된 근거에서 별도 요구사항 구조는 확인되지 않았습니다.";

      const directPenalties = (detail.penalties || []).filter(Boolean);
      const candidatePenalties = (detail.candidate_penalties || []).filter(Boolean).slice(0, 5);
      const otherWarnings = (detail.warnings || []).filter(
        (warning) => !["DIRECT_PENALTY_NOT_FOUND", "CANDIDATE_PENALTY_REQUIRES_REVIEW"].includes(warning.warning_type)
      );

      setSelectedLaw({
        title: detail.title || detail.law_name || fallbackTitle || nodeId,
        subtitle: [detail.law_name, detail.article_no, detail.annex_title].filter(Boolean).join(" / "),
        text: sourceText,
        formattedText: legalPreview(sourceText, 1400),
        fullText: normalizeLegalText(sourceText),
        summary: normalizeLegalText(detail.summary),
        why: normalizeLegalText(detail.why_relevant),
        related: normalizeLegalText(relatedText),
        requirements: requirementText,
        requirementItems: splitBulletText(requirementText, 8),
        penalty: "",
        penalties: directPenalties,
        candidatePenalties,
        citations,
        warnings: otherWarnings,
        nodeId,
      });
    } catch (error) {
      setLawError(error.message || "법령 상세를 불러오지 못했습니다.");
      setSelectedLaw({
        title: fallbackTitle || nodeId,
        subtitle: "",
        text: "법령 상세 조회에 실패했습니다.",
        formattedText: "법령 상세 조회에 실패했습니다.",
        fullText: "",
        related: "잠시 후 다시 시도하세요.",
        requirements: "",
        requirementItems: [],
        penalties: [],
        candidatePenalties: [],
        citations: [],
        warnings: [],
        nodeId,
      });
    } finally {
      setLawLoading(false);
    }
  };

  const submitQuestion = async (rawText, clearInput) => {
    if (!rawText.trim() || chatSending) return;
    const userText = rawText.trim();
    const userMessage = { role: "user", text: userText };
    setChatMessages((prev) => [...prev, userMessage]);
    clearInput("");
    setChatSending(true);

    try {
      const result = await askChat({
        question: userText,
        mode: "qa",
        chat_history: chatMessages
          .filter((message) => message.role === "user" || message.role === "assistant")
          .map((message) => ({ role: message.role, content: message.text })),
      });
      const firstEvidence = result.evidences?.[0];
      const assistantMessage = {
        role: "assistant",
        text: result.answer || "답변 본문이 비어 있습니다.",
        law: firstEvidence?.law_name || firstEvidence?.title || null,
        node_id: firstEvidence?.node_id || null,
        evidences: result.evidences || [],
        citations: result.citations || [],
        evidence_chips: result.evidence_chips || [],
        confirmed_penalties: result.confirmed_penalties || [],
        candidate_penalties: result.candidate_penalties || [],
        legal_chains: result.legal_chains || [],
        evidence_readiness: result.evidence_readiness || null,
        answer_policy: result.answer_policy || null,
        claim_check: result.claim_check || null,
        warnings: result.warnings || [],
        missing_evidence: result.missing_evidence || [],
        evidence_pack: result.evidence_pack || null,
      };
      setChatMessages((prev) => [...prev, assistantMessage]);
      saveQuietly(
        saveChatHistory({
          project_id: selectedProjectId,
          site_name: siteName,
          question: userText,
          answer: result.answer,
          evidences: result.evidences || [],
          citations: result.citations || [],
          evidence_chips: result.evidence_chips || [],
          confirmed_penalties: result.confirmed_penalties || [],
          candidate_penalties: result.candidate_penalties || [],
          legal_chains: result.legal_chains || [],
          evidence_readiness: result.evidence_readiness || null,
          answer_policy: result.answer_policy || null,
          claim_check: result.claim_check || null,
          warnings: result.warnings || [],
          missing_evidence: result.missing_evidence || [],
          evidence_pack: result.evidence_pack || null,
        }).then(refreshHistory)
      );
    } catch (error) {
      setChatMessages((prev) => [
        ...prev,
        { role: "assistant", text: error.message || "답변을 불러오지 못했습니다.", error: true },
      ]);
    } finally {
      setChatSending(false);
    }
  };

  const sendQa = () => submitQuestion(qaInput, setQaInput);

  const saveExportEvent = () => {
    saveQuietly(
      saveExportHistory({
        project_id: selectedProjectId,
        site_name: siteName,
        format: "pdf",
        item_count: checklistItems.length,
      }).then(refreshHistory)
    );
  };

  const renderLawPanel = () => {
    const weakSummary = selectedLaw ? isWeakSummary(selectedLaw.summary, selectedLaw.text) : true;
    return (
      <section className="panel law-panel">
        {lawLoading ? (
          <div className="empty-state">법령 상세를 불러오는 중입니다.</div>
        ) : !selectedLaw ? (
          <div className="empty-state">근거를 선택하면 이곳에 법령 상세가 표시됩니다.</div>
        ) : (
          <>
            {lawError && <div className="error-box">{lawError}</div>}
            <div className="law-title">{selectedLaw.title}</div>
            {selectedLaw.subtitle && <div className="law-meta">{selectedLaw.subtitle}</div>}

            <div className="law-section-title">{weakSummary ? "근거 안내" : "요약"}</div>
            <div className="law-card subtle legal-text">
              {weakSummary
                ? selectedLaw.subtitle
                  ? `${selectedLaw.subtitle}에 연결된 근거입니다. 아래 원문과 관련 근거를 함께 확인하세요.`
                  : "선택한 항목과 연결된 법령 근거입니다. 아래 원문과 관련 근거를 함께 확인하세요."
                : normalizeLegalText(selectedLaw.summary)}
            </div>

            <div className="law-section-title">조문 원문 또는 근거 내용</div>
            <div className="law-card legal-text">{selectedLaw.formattedText || legalPreview(selectedLaw.text, 1400)}</div>
            {selectedLaw.fullText && selectedLaw.fullText.length > 1400 && (
              <details className="law-text-details">
                <summary>원문 전체 보기</summary>
                <div className="law-card legal-text full">{selectedLaw.fullText}</div>
              </details>
            )}

            {selectedLaw.why && (
              <>
                <div className="law-section-title">이 항목과 연결된 이유</div>
                <div className="law-card subtle legal-text">{normalizeLegalText(selectedLaw.why)}</div>
              </>
            )}

            <div className="law-section-title">연결된 근거</div>
            <div className="law-card subtle legal-text">{normalizeLegalText(selectedLaw.related)}</div>

            {!!selectedLaw.requirements && (
              <>
                <div className="law-section-title">확인해야 할 사항</div>
                {selectedLaw.requirementItems?.length > 1 ? (
                  <ul className="law-bullet-list">
                    {selectedLaw.requirementItems.map((line, idx) => (
                      <li key={`req-${idx}`}>{line}</li>
                    ))}
                  </ul>
                ) : (
                  <div className="law-card subtle legal-text">{normalizeLegalText(selectedLaw.requirements)}</div>
                )}
              </>
            )}

            <div className="law-section-title">위반 시 예상 처벌</div>
            {selectedLaw.penalties?.length > 0 ? (
              <>
                <div className="law-card penalty-guide direct-guide">
                  현재 근거와 직접 연결된 처벌 관련 조항입니다. 실제 적용 여부는 구체적 사실관계와 함께 검토해야 합니다.
                </div>
                <div className="penalty-list">
                  {selectedLaw.penalties.slice(0, 5).map((penalty, idx) => (
                    <div className="penalty-card direct" key={`direct-${penalty.rule_id || idx}`}>
                      <div className="penalty-card-head">
                        <strong>{[penalty.law_name, penalty.article_no].filter(Boolean).join(" ") || "직접 연결된 처벌 근거"}</strong>
                        <span className="badge danger">직접 연결</span>
                      </div>
                      <div className="penalty-preview legal-text">{legalPreview(penalty.preview || penalty.text || "본문 preview가 없습니다.", 700)}</div>
                      <div className="penalty-meta">
                        match: {penalty.match_type || "DIRECT_LINKED"} · confidence: {penalty.confidence || "high"}
                      </div>
                    </div>
                  ))}
                </div>
              </>
            ) : selectedLaw.candidatePenalties?.length > 0 ? (
              <div className="law-card penalty-guide candidate-guide">
                직접 연결된 처벌 근거는 확인되지 않았습니다. 다만 관련 가능성이 있는 벌칙·과태료 조항 후보가 있어 원문 검토가 필요합니다.
              </div>
            ) : (
              <div className="law-card danger-box legal-text">
                현재 연결된 근거에서는 직접 처벌 조항이 확인되지 않았습니다. 처벌 여부는 별도의 벌칙·과태료 조항과 함께 검토해야 합니다.
              </div>
            )}

            {selectedLaw.candidatePenalties?.length > 0 && (
              <>
                <div className="law-section-title">관련 가능성이 있는 벌칙·과태료 조항 후보</div>
                <div className="law-card warning-box legal-text">
                  아래 항목은 조항 번호 참조 등을 기준으로 찾은 후보입니다. 직접 연결된 처벌 결론이 아니므로 실제 적용 여부는 원문 검토가 필요합니다.
                </div>
                <div className="penalty-list candidate-visible">
                  {selectedLaw.candidatePenalties.map((penalty, idx) => (
                    <div className="penalty-card candidate emphasized" key={`candidate-${penalty.rule_id || idx}`}>
                      <div className="penalty-card-head">
                        <strong>{[penalty.law_name, penalty.article_no].filter(Boolean).join(" ") || penalty.title || "후보 처벌 근거"}</strong>
                        <span className="badge warning">후보</span>
                        <span className="badge info">검토 필요</span>
                        <span className="badge info">확정 아님</span>
                      </div>
                      <div className="penalty-preview legal-text">{legalPreview(penalty.preview || penalty.text || "본문 preview가 없습니다.", 700)}</div>
                      <div className="penalty-meta">
                        match: {penalty.match_type || "ARTICLE_REFERENCE_MATCH"} · confidence: {penalty.confidence || "medium"}
                      </div>
                      {penalty.match_reason && <div className="penalty-notice legal-text">{normalizeLegalText(penalty.match_reason)}</div>}
                      {penalty.candidate_notice && <div className="penalty-notice legal-text">{normalizeLegalText(penalty.candidate_notice)}</div>}
                    </div>
                  ))}
                </div>
              </>
            )}

            {!!selectedLaw.citations?.length && (
              <>
                <div className="law-section-title">관련 근거 출처</div>
                <div className="detail-list">
                  {selectedLaw.citations.slice(0, 6).map((citation, idx) => (
                    <div className="detail-item" key={`law-citation-${idx}`}>
                      <strong>{citation.citation_text || [citation.law_name, citation.article_no].filter(Boolean).join(" ") || "근거 위치"}</strong>
                      <small>{[citation.evidence_kind, citation.confidence].filter(Boolean).join(" · ")}</small>
                    </div>
                  ))}
                </div>
              </>
            )}

            {!!selectedLaw.warnings?.length && (
              <div className="law-card warning-box legal-text">
                {dedupeByMessage(selectedLaw.warnings)
                  .map((warning) => userFacingWarning(warning))
                  .join("\n")}
              </div>
            )}

            {selectedLaw.nodeId && (
              <details className="law-debug">
                <summary>개발자용 연결 ID</summary>
                <code>{selectedLaw.nodeId}</code>
              </details>
            )}
          </>
        )}
      </section>
    );
  };

  const renderAnswerCard = (msg, idx) => {
    if (msg.role === "user") {
      return (
        <div key={`qa-user-${idx}`} className="qa-message-row user">
          <div className="qa-bubble user-bubble">
            <div className="answer-role">질문</div>
            <div>{msg.text}</div>
          </div>
        </div>
      );
    }

    const policy = answerPolicyInfo(msg.answer_policy);
    const chips = fallbackEvidenceChips(msg);
    const visibleChips = chips.slice(0, 8);
    const hiddenChips = chips.slice(8);
    const warnings = dedupeByMessage(msg.warnings || []);
    const missingEvidence = dedupeByMessage(msg.missing_evidence || []);
    const claimIssues = msg.claim_check?.issues || [];
    const citations = msg.citations || [];
    const evidences = msg.evidences || [];
    const confirmedPenalties = msg.confirmed_penalties || [];
    const candidatePenalties = msg.candidate_penalties || [];
    const evidencePack = msg.evidence_pack || {};
    const cleanedAnswer = cleanAnswerText(msg.text);
    const answerSections = parseAnswerSections(cleanedAnswer);
    const mainSections = answerSections.filter((section) => !["근거"].includes(section.title));
    const basisSections = answerSections.filter((section) => ["근거"].includes(section.title));

    return (
      <div key={`qa-assistant-${idx}`} className="qa-message-row assistant">
        <div className={`qa-bubble assistant-bubble ${msg.answer_policy === "INDIRECT_ONLY_RESPONSE" ? "limited" : ""}`}>
          <div className="answer-role">답변</div>
          <div className="answer-section-list">
            {(mainSections.length ? mainSections : answerSections).map((section, sectionIdx) => (
              <div className="answer-section" key={`answer-section-${sectionIdx}`}>
                {section.title !== "답변" && <div className="answer-section-title">{section.title}</div>}
                <div className="answer-body legal-text">{legalPreview(section.body, 1100)}</div>
              </div>
            ))}
          </div>

          {!!basisSections.length && (
            <details className="law-text-details">
              <summary>답변에 사용된 근거 문장 보기</summary>
              {basisSections.map((section, sectionIdx) => (
                <div className="law-card legal-text full" key={`basis-section-${sectionIdx}`}>
                  {legalPreview(section.body, 1400)}
                </div>
              ))}
            </details>
          )}

          {(confirmedPenalties.length > 0 || candidatePenalties.length > 0) && (
            <div className="penalty-connection-panel">
              <div className="mini-section-title">의무-처벌 연결</div>
              <div className="penalty-connection-summary">
                <span className={confirmedPenalties.length ? "badge danger" : "badge info"}>
                  직접 연결 {confirmedPenalties.length}건
                </span>
                <span className={candidatePenalties.length ? "badge warning" : "badge info"}>
                  후보 연결 {candidatePenalties.length}건
                </span>
              </div>
              {!!confirmedPenalties.length && (
                <div className="penalty-connection-list">
                  {confirmedPenalties.slice(0, 4).map((penalty, penaltyIdx) => (
                    <div className="penalty-connection-item direct" key={`qa-direct-penalty-${penaltyIdx}`}>
                      <strong>{[penalty.law_name, penalty.article_no].filter(Boolean).join(" ") || "직접 연결된 처벌 근거"}</strong>
                      <span>{previewText(penalty.source_text_preview || penalty.source_text || penalty.preview || "", 180)}</span>
                    </div>
                  ))}
                </div>
              )}
              {!!candidatePenalties.length && (
                <details className="chat-details compact" open={!confirmedPenalties.length}>
                  <summary>후보 처벌 근거 보기</summary>
                  <div className="penalty-connection-list">
                    {candidatePenalties.slice(0, 6).map((penalty, penaltyIdx) => (
                      <div className="penalty-connection-item candidate" key={`qa-candidate-penalty-${penaltyIdx}`}>
                        <strong>{[penalty.law_name, penalty.article_no].filter(Boolean).join(" ") || "후보 처벌 근거"}</strong>
                        <span>{previewText(penalty.source_text_preview || penalty.source_text || penalty.preview || "", 190)}</span>
                        <small>
                          {[penalty.candidate_status, penalty.relation_type || penalty.match_type, penalty.confidence]
                            .filter(Boolean)
                            .join(" · ")}
                        </small>
                      </div>
                    ))}
                  </div>
                </details>
              )}
            </div>
          )}

          {(msg.evidence_readiness || msg.answer_policy || msg.claim_check) && (
            <div className={`claim-check-panel ${msg.answer_policy === "INDIRECT_ONLY_RESPONSE" ? "limited" : ""}`}>
              <div className="claim-check-head">
                <span className={`badge ${policy.className}`}>{policy.label}</span>
                {msg.evidence_readiness && <span className={readinessBadgeClass(msg.evidence_readiness)}>{badgeLabel(msg.evidence_readiness)}</span>}
                {msg.claim_check?.claim_check_status && <span className="badge info">{msg.claim_check.claim_check_status}</span>}
              </div>
              <div className="claim-check-desc">{policy.description}</div>
              {!!msg.claim_check?.badges?.length && (
                <div className="graph-rag-badges">
                  {msg.claim_check.badges.map((badge, badgeIdx) => (
                    <span key={badgeIdx} className={`badge ${badge.severity || "info"}`} title={badge.message || ""}>
                      {badge.label || badge.severity || "claim"}
                    </span>
                  ))}
                </div>
              )}
              {!!claimIssues.length && (
                <div className="claim-issue-list">
                  <div className="mini-section-title">확인된 제한사항</div>
                  {claimIssues.slice(0, 5).map((issue, issueIdx) => (
                    <div key={`qa-issue-${issueIdx}`}>
                      <span className={readinessBadgeClass(issue.severity)}>{issue.severity || "info"}</span> {userFacingWarning(issue)}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {!!chips.length && (
            <div className="connected-evidence-panel">
              <div className="mini-section-title">연결된 근거</div>
              <div className="evidence-chip-list">
                {visibleChips.map((chip, chipIdx) => {
                  const nodeId = chipNodeId(chip);
                  return (
                    <button
                      key={`${chip.id || chipLabel(chip)}-${chipIdx}`}
                      type="button"
                      className={`evidence-chip ${chip.severity || "normal"} ${nodeId ? "" : "disabled"}`}
                      title={nodeId ? "근거 상세 열기" : "상세 조회 ID 없음"}
                      disabled={!nodeId}
                      onClick={() => nodeId && openLaw(nodeId)}
                    >
                      <span>{chipLabel(chip)}</span>
                      <small>
                        {chip.type || chip.evidence_kind || "근거"}
                        {chip.preview ? ` · ${previewText(chip.preview, 120)}` : ""}
                      </small>
                    </button>
                  );
                })}
              </div>
              {!!hiddenChips.length && (
                <details className="chat-details compact">
                  <summary>추가 근거 {hiddenChips.length}개 더 보기</summary>
                  <div className="evidence-chip-list">
                    {hiddenChips.map((chip, chipIdx) => {
                      const nodeId = chipNodeId(chip);
                      return (
                        <button
                          key={`${chip.id || chipLabel(chip)}-hidden-${chipIdx}`}
                          type="button"
                          className={`evidence-chip ${chip.severity || "normal"} ${nodeId ? "" : "disabled"}`}
                          disabled={!nodeId}
                          onClick={() => nodeId && openLaw(nodeId)}
                        >
                          <span>{chipLabel(chip)}</span>
                          <small>{chip.type || chip.evidence_kind || "근거"}</small>
                        </button>
                      );
                    })}
                  </div>
                </details>
              )}
            </div>
          )}

          {(warnings.length > 0 || missingEvidence.length > 0) && (
            <div className="evidence-warning-panel">
              {!!warnings.length && (
                <>
                  <div className="mini-section-title">주의사항</div>
                  {warnings.slice(0, 5).map((warning, warningIdx) => (
                    <div key={`qa-w-${warningIdx}`} className="warning-row">
                      {warning.severity && <span className={readinessBadgeClass(warning.severity)}>{warning.severity}</span>}
                      <span>{userFacingWarning(warning)}</span>
                    </div>
                  ))}
                </>
              )}
              {!!missingEvidence.length && (
                <>
                  <div className="mini-section-title">추가로 필요한 근거</div>
                  <div className="missing-help">이 질문에 더 정확히 답하려면 다음 근거가 필요합니다.</div>
                  {missingEvidence.slice(0, 5).map((missing, missingIdx) => (
                    <div key={`qa-m-${missingIdx}`} className="warning-row">
                      <span>{itemText(missing, "추가 근거 항목")}</span>
                    </div>
                  ))}
                </>
              )}
            </div>
          )}

          {(citations.length > 0 || evidences.length > 0 || evidencePack.primary_evidence_count !== undefined) && (
            <details className="chat-details">
              <summary>근거 상세 보기</summary>
              {(evidencePack.primary_evidence_count !== undefined || evidencePack.supporting_evidence_count !== undefined) && (
                <div className="evidence-counts">
                  <span>primary {evidencePack.primary_evidence_count ?? 0}</span>
                  <span>supporting {evidencePack.supporting_evidence_count ?? 0}</span>
                </div>
              )}
              {!!citations.length && (
                <div className="detail-list">
                  <div className="mini-section-title">근거 출처</div>
                  {citations.slice(0, 8).map((citation, citationIdx) => (
                    <div className="detail-item" key={`qa-citation-${citationIdx}`}>
                      <strong>{citation.citation_text || [citation.law_name, citation.article_no].filter(Boolean).join(" ") || "근거 위치"}</strong>
                      <small>{[citation.law_name, citation.article_no, citation.annex_title, citation.evidence_kind, citation.confidence].filter(Boolean).join(" · ")}</small>
                    </div>
                  ))}
                </div>
              )}
              {!!evidences.length && (
                <div className="detail-list">
                  <div className="mini-section-title">호환 근거</div>
                  {evidences.slice(0, 8).map((evidence, evidenceIdx) => (
                    <div className="detail-item" key={`qa-evidence-${evidenceIdx}`}>
                      <strong>{evidence.title || evidence.law_name || evidence.type || "근거"}</strong>
                      <small>{[evidence.law_name, evidence.type, evidence.score].filter(Boolean).join(" · ")}</small>
                      {evidence.source_text && <div>{previewText(evidence.source_text, 250)}</div>}
                    </div>
                  ))}
                </div>
              )}
            </details>
          )}
        </div>
      </div>
    );
  };

  const renderOptionGroup = (label, values, selected, setter) => (
    <div className="form-block">
      <label>{label}</label>
      <div className="pill-grid">
        {values.map((value) => (
          <button
            key={value}
            type="button"
            className={selected.includes(value) ? "pill selected" : "pill"}
            onClick={() => setter((prev) => toggleValue(prev, value))}
          >
            {value}
          </button>
        ))}
      </div>
    </div>
  );

  return (
    <div className={sidebarOpen ? "app-shell" : "app-shell sidebar-collapsed"}>
      <aside className="sidebar">
        <div className="sidebar-project">
          <div className="sidebar-label">현장 프로젝트</div>
          <select value={selectedProjectId} onChange={(e) => setSelectedProjectId(e.target.value)} className="select">
            {projects.map((project) => (
              <option key={project.id} value={project.id}>
                {project.name}
              </option>
            ))}
          </select>
          <button
            className="ghost-button full"
            onClick={() => {
              const newProject = { id: `p-${Date.now()}`, name: `새 현장 ${projects.length + 1}`, updatedAt: new Date().toISOString().slice(0, 10) };
              setProjects((prev) => [...prev, newProject]);
              setSelectedProjectId(newProject.id);
              saveQuietly(createProject(newProject));
            }}
          >
            새 현장 추가
          </button>
        </div>

        <nav className="sidebar-nav">
          {[
            ["checklist", "체크리스트"],
            ["qa", "법령 QA"],
            ["explore", "근거 탐색"],
            ["validation", "검증·리포트"],
            ["history", "History"],
          ].map(([key, label]) => (
            <button key={key} className={page === key ? "nav-item active" : "nav-item"} onClick={() => setPage(key)}>
              {label}
            </button>
          ))}
        </nav>
      </aside>

      <main className="main">
        <header className="topbar">
          <div className="topbar-title-row">
            <button
              type="button"
              className="sidebar-toggle"
              onClick={() => setSidebarOpen((value) => !value)}
              aria-label={sidebarOpen ? "메뉴 닫기" : "메뉴 열기"}
              title={sidebarOpen ? "메뉴 닫기" : "메뉴 열기"}
            >
              {sidebarOpen ? <PanelLeftClose size={18} /> : <Menu size={18} />}
            </button>
          </div>
          <div className="topbar-copy">
            <h1>{selectedProject?.name || siteName}</h1>
            <p>산업안전 법령 근거를 기준으로 체크리스트, QA, 근거 검증을 확인합니다.</p>
          </div>
          <button className="button" onClick={saveExportEvent}>PDF 출력</button>
        </header>

        {page === "checklist" && (
          <div className="checklist-layout">
            <section className="panel input-panel">
              <div className="section-heading">현장 조건 입력</div>
              <div className="form-block">
                <label>현장명</label>
                <input className="input" value={siteName} onChange={(e) => setSiteName(e.target.value)} />
              </div>
              <div className="form-row">
                <div className="form-block">
                  <label>업종</label>
                  <input className="input" value={industry} onChange={(e) => setIndustry(e.target.value)} />
                </div>
                <div className="form-block">
                  <label>근로자 수</label>
                  <input className="input" type="number" value={workerCount} onChange={(e) => setWorkerCount(e.target.value)} />
                </div>
              </div>
              {renderOptionGroup("작업 형태", workTypeOptions, workTypes, setWorkTypes)}
              {renderOptionGroup("작업 환경", environmentOptions, environments, setEnvironments)}
              {renderOptionGroup("위험 요인", riskFactorOptions, hazards, setHazards)}
              <div className="form-block">
                <label>안전 관리 상태</label>
                <div className="safety-list">
                  {safetyItems.map((item) => (
                    <label key={item} className="checkbox-row">
                      <input
                        type="checkbox"
                        checked={Boolean(safetyState[item])}
                        onChange={() => setSafetyState((prev) => ({ ...prev, [item]: !prev[item] }))}
                      />
                      {item}
                    </label>
                  ))}
                </div>
              </div>
              <div className="form-block">
                <label>특이사항</label>
                <textarea className="textarea" value={specialNotes} onChange={(e) => setSpecialNotes(e.target.value)} />
              </div>
              <button className="primary-button full" onClick={generateChecklist} disabled={checklistLoading}>
                {checklistLoading ? "생성 중..." : "체크리스트 생성"}
              </button>
            </section>

            <section className="panel checklist-panel">
              <div className="section-heading">체크리스트 항목</div>
              <div className="filter-row">
                {[
                  ["all", "전체"],
                  ["high", "고위험"],
                  ["unchecked", "미완료"],
                  ["evidence_linked", "근거 연결"],
                  ["candidate_penalty", "벌칙·과태료 후보"],
                  ["direct_penalty", "처벌 관련 근거"],
                  ["needs_review", "검토 참고"],
                ].map(([key, label]) => (
                  <button key={key} className={checklistFilter === key ? "filter active" : "filter"} onClick={() => setChecklistFilter(key)}>
                    {label}
                  </button>
                ))}
              </div>
              <div className="checklist-summary-row">
                <span>총 {checklistItems.length}개</span>
                <span>준수율 {complianceRate}%</span>
                <button className="ghost-button" onClick={addCustomItem}>직접 항목 추가</button>
              </div>
              <div className="check-list">
                {!filteredChecklist.length ? (
                  <div className="empty-state">아직 생성된 체크리스트가 없습니다.</div>
                ) : (
                  filteredChecklist.map((item) => {
                    const badge = riskLabel(item.risk);
                    return (
                      <div key={item.id} className={item.completed ? "check-item completed" : "check-item"}>
                        <input
                          type="checkbox"
                          checked={Boolean(item.completed)}
                          onChange={() =>
                            setChecklistItems((prev) => prev.map((row) => (row.id === item.id ? { ...row, completed: !row.completed } : row)))
                          }
                        />
                        <div className="check-item-body">
                          <div className="check-topline">
                            <div className="check-text">{item.title || item.text}</div>
                            <span className={badge.className}>{badge.text}</span>
                          </div>
                          {(item.law_title || item.law || item.description) && (
                            <div className="check-summary">
                              {item.law_title || item.law}
                              {item.description ? ` · ${previewText(item.description, 120)}` : ""}
                            </div>
                          )}
                          <div className="check-primary-badges">
                            {hasLinkedEvidence(item) ? <span className="badge success">근거 연결됨</span> : <span className="badge info">근거 미연결</span>}
                            {hasDirectPenalty(item) && <span className="badge danger soft-danger">처벌 관련 근거 있음</span>}
                            {hasCandidatePenalty(item) && <span className="badge warning strong-warning">벌칙·과태료 후보 {item.candidate_penalties.length}건</span>}
                          </div>
                          <div className="check-secondary-row">
                            {item.autoCheck && <span className="badge success secondary-badge">자동체크</span>}
                            {item.custom && <span className="badge info secondary-badge">직접추가</span>}
                            {needsSecondaryReview(item) && <span className="badge info secondary-badge">추가 검토 참고</span>}
                            <button className="law-button" onClick={() => openLaw(item)}>근거 보기</button>
                          </div>
                          {hasCandidatePenalty(item) && (
                            <div className="check-penalty-hint">후보 처벌은 확정 결론이 아니며, 실제 적용 여부는 원문 검토가 필요합니다.</div>
                          )}
                        </div>
                      </div>
                    );
                  })
                )}
              </div>
            </section>

            {renderLawPanel()}
          </div>
        )}

        {page === "qa" && (
          <div className="qa-layout qa-chat-page">
            <section className="panel qa-main-panel qa-chat-panel">
              <div className="qa-chat-header">
                <div>
                  <div className="qa-title">법령 QA 상담</div>
                  <div className="qa-description">산업안전 법령 근거를 바탕으로 답변하고, 직접 근거·간접 근거·부족 근거를 함께 표시합니다.</div>
                </div>
              </div>
              <div className="qa-example-questions">
                {[
                  "안전관리자는 어떤 기준으로 선임해야 하나?",
                  "정기 안전보건교육은 몇 시간 해야 하나?",
                  "안전검사 대상 기계에는 어떤 것들이 있나?",
                  "위험성평가 결과를 근로자에게 알려야 하나?",
                  "과태료가 부과되는 경우는 무엇인가?",
                  "적용 제외되는 경우가 있나?",
                ].map((question) => (
                  <button key={question} type="button" className="example-question" onClick={() => setQaInput(question)}>
                    {question}
                  </button>
                ))}
              </div>
              <div className="qa-conversation">
                {qaMessages.length === 0 ? (
                  <div className="empty-state qa-empty">질문을 입력하면 답변과 근거 상태가 대화 형식으로 표시됩니다.</div>
                ) : (
                  qaMessages.map((message, idx) => renderAnswerCard(message, idx))
                )}
              </div>
              <div className="qa-input-sticky">
                <input
                  className="input qa-question-input"
                  value={qaInput}
                  onChange={(e) => setQaInput(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && sendQa()}
                  placeholder="산업안전 법령에 대해 질문하세요. 예: 정기 안전보건교육은 몇 시간 해야 하나?"
                />
                <button className="primary-button inline" onClick={sendQa} disabled={chatSending}>
                  {chatSending ? "질문 중..." : "보내기"}
                </button>
              </div>
            </section>
            {renderLawPanel()}
          </div>
        )}

        {page === "explore" && (
          <div className="explore-layout">
            <section className="panel explore-panel">
              <div className="explore-intro">
                <div className="section-heading">근거 탐색</div>
                <p>질문이나 체크리스트 항목별로 어떤 근거가 연결되었는지 다시 확인하는 공간입니다.</p>
              </div>
              <input
                className="input"
                value={exploreQuery}
                onChange={(e) => setExploreQuery(e.target.value)}
                placeholder="질문, 체크리스트 항목, 법령명, 조문번호로 검색하세요"
              />
              <details className="advanced-node-search">
                <summary>고급: 내부 ID로 직접 조회</summary>
                <div className="node-search-row">
                  <input
                    className="input"
                    value={exploreNodeId}
                    onChange={(e) => setExploreNodeId(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && exploreNodeId.trim() && openLaw(exploreNodeId.trim())}
                    placeholder="개발자 확인용 node id"
                  />
                  <button className="button" onClick={() => exploreNodeId.trim() && openLaw(exploreNodeId.trim())}>조회</button>
                </div>
              </details>

              <div className="section-heading">질문/항목별 연결 근거</div>
              {evidenceGroups.length === 0 ? (
                <div className="empty-state">아직 연결된 근거가 없습니다. 법령 QA에서 질문하거나 체크리스트를 생성하면 질문/항목별 근거가 이곳에 쌓입니다.</div>
              ) : (
                evidenceGroups.map((group) => (
                  <div className="evidence-group-card" key={group.id}>
                    <div className="evidence-group-head">
                      <div>
                        <div className="evidence-group-type">{group.groupType === "qa" ? "질문별 연결 근거" : "체크리스트 항목별 연결 근거"}</div>
                        <div className="evidence-group-title">{group.title}</div>
                        {group.answerPreview && <div className="evidence-group-preview">{group.answerPreview}</div>}
                      </div>
                      <div className="evidence-group-badges">
                        {group.answer_policy && <span className={readinessBadgeClass(group.answer_policy)}>{badgeLabel(group.answer_policy)}</span>}
                        {group.evidence_readiness && <span className={readinessBadgeClass(group.evidence_readiness)}>{badgeLabel(group.evidence_readiness)}</span>}
                        <span className="badge info">근거 {group.items.length}개</span>
                        {group.candidatePenaltyCount > 0 && <span className="badge warning">처벌 후보 {group.candidatePenaltyCount}건</span>}
                      </div>
                    </div>
                    <details className="evidence-group-details" open>
                      <summary>연결 근거 보기</summary>
                      <div className="explore-list grouped">
                        {group.items.map((row, rowIdx) => (
                          <button
                            key={`${group.id}-${row.id}-${rowIdx}`}
                            className={row.node_id ? "explore-item" : "explore-item disabled"}
                            disabled={!row.node_id}
                            onClick={() => row.node_id && openLaw(row.node_id)}
                          >
                            <div className="explore-item-head">
                              <strong>{row.label}</strong>
                              <span className="badge info">{row.type}</span>
                            </div>
                            {row.preview && <div className="explore-preview">{previewText(row.preview, 180)}</div>}
                          </button>
                        ))}
                      </div>
                    </details>
                  </div>
                ))
              )}
            </section>
            {renderLawPanel()}
          </div>
        )}

        {page === "validation" && (
          <div className="validation-page">
            <div className="validation-grid">
              <div className="stat-card"><div className="stat-label">검토한 답변</div><div className="stat-value">{validationStats.answerMessages.length}</div></div>
              <div className="stat-card"><div className="stat-label">직접 답변 가능</div><div className="stat-value">{validationStats.direct}</div></div>
              <div className="stat-card"><div className="stat-label">조건 확인 필요</div><div className="stat-value">{validationStats.caution}</div></div>
              <div className="stat-card"><div className="stat-label">직접 단정 불가</div><div className="stat-value red">{validationStats.indirect}</div></div>
            </div>
            <div className="validation-layout">
              <section className="panel validation-panel">
                <div className="section-heading">답변 품질 점검표</div>
                <div className="validation-help">
                  이 페이지는 최근 답변이 실무 검토에 사용할 수 있는 수준인지 점검하는 화면입니다. 근거 수, 부족 근거, 단정 가능 여부를 답변별로 확인합니다.
                </div>
                <div className="validation-list">
                  {validationStats.answerMessages.length === 0 ? (
                    <div className="empty-state">아직 검증할 QA 답변이 없습니다.</div>
                  ) : (
                    validationStats.answerMessages.slice(-10).reverse().map((message, idx) => {
                      const verdict = qualityVerdict(message);
                      const messageIndex = chatMessages.indexOf(message);
                      const question = [...chatMessages.slice(0, messageIndex)].reverse().find((row) => row.role === "user")?.text;
                      const chips = fallbackEvidenceChips(message);
                      return (
                        <div className="quality-card" key={`quality-${idx}`}>
                          <div className="quality-head">
                            <span className={`badge ${verdict.className}`}>{verdict.label}</span>
                            {message.evidence_readiness && <span className={readinessBadgeClass(message.evidence_readiness)}>{badgeLabel(message.evidence_readiness)}</span>}
                          </div>
                          <div className="quality-question">질문: {question || "질문 정보 없음"}</div>
                          <div className="quality-answer">답변 요약: {previewText(cleanAnswerText(message.text), 220)}</div>
                          <div className="quality-desc">{verdict.description}</div>
                          <div className="quality-metrics">
                            <span>근거 {chips.length}개</span>
                            <span>주의 {message.warnings?.length || 0}개</span>
                            <span>부족 근거 {message.missing_evidence?.length || 0}개</span>
                          </div>
                          <div className="quality-next">다음 행동: {verdict.nextAction}</div>
                          {!!chips.length && (
                            <details className="quality-evidence">
                              <summary>사용된 근거 보기</summary>
                              <div className="evidence-chip-list">
                                {chips.slice(0, 8).map((chip, chipIdx) => {
                                  const nodeId = chipNodeId(chip);
                                  return (
                                    <button
                                      key={`quality-chip-${chipIdx}`}
                                      className={`evidence-chip ${nodeId ? "" : "disabled"}`}
                                      disabled={!nodeId}
                                      onClick={() => nodeId && openLaw(nodeId)}
                                    >
                                      <span>{chipLabel(chip)}</span>
                                      <small>{chip.type || chip.evidence_kind || "근거"}</small>
                                    </button>
                                  );
                                })}
                              </div>
                            </details>
                          )}
                        </div>
                      );
                    })
                  )}
                </div>
              </section>
              <section className="panel validation-panel">
                <div className="section-heading">직접 근거 없는 단정 방지</div>
                <div className="guardrail-card">
                  <div className="guardrail-title">위험성평가 결과 고지 질문</div>
                  <p>
                    위험성평가 결과 고지 질문처럼 현재 KB에서 직접 근거가 확인되지 않은 경우, 시스템은 의무를 단정하지 않고
                    간접 근거 기반의 제한 답변으로 표시합니다. 이는 법령 근거가 없는 단정을 막기 위한 안전장치입니다.
                  </p>
                  <div className="graph-rag-badges">
                    <span className="badge warning">INDIRECT_ONLY</span>
                    <span className="badge warning">INDIRECT_ONLY_RESPONSE</span>
                  </div>
                  <button
                    className="button"
                    onClick={() => {
                      setPage("qa");
                      setQaInput("위험성평가 결과를 근로자에게 알려야 하나?");
                    }}
                  >
                    QA 페이지에서 확인
                  </button>
                </div>
              </section>
            </div>
          </div>
        )}

        {page === "history" && (
          <div className="history-page">
            <section className="panel">
              <div className="section-heading">History</div>
              <div className="history-grid">
                <div>
                  <h3>최근 채팅</h3>
                  {(historyRows.chats || []).slice(-8).reverse().map((row, idx) => (
                    <div className="history-item" key={`chat-history-${idx}`}>
                      <strong>{row.question || "질문"}</strong>
                      <div>{previewText(row.answer, 160)}</div>
                    </div>
                  ))}
                </div>
                <div>
                  <h3>최근 체크리스트</h3>
                  {(historyRows.checklists || []).slice(-8).reverse().map((row, idx) => (
                    <div className="history-item" key={`check-history-${idx}`}>
                      <strong>{row.site_name || "현장"}</strong>
                      <div>{row.items?.length || row.item_count || 0}개 항목</div>
                    </div>
                  ))}
                </div>
                <div>
                  <h3>최근 출력</h3>
                  {(historyRows.exports || []).slice(-8).reverse().map((row, idx) => (
                    <div className="history-item" key={`export-history-${idx}`}>
                      <strong>{row.format || "export"}</strong>
                      <div>{row.item_count || 0}개 항목</div>
                    </div>
                  ))}
                </div>
              </div>
            </section>
          </div>
        )}
      </main>
    </div>
  );
}
