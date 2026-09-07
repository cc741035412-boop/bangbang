import { useMemo, useState } from "react";
import { createSelectionQueue, type SelectionState } from "./selection-queue";
import { useInfiniteQuery, useIsMutating, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiClient } from "../../api/client";
import { readToken, requestJson } from "../../api/http";
import type { components } from "../../api/generated/schema";

export type Observation = components["schemas"]["ObservationResponse"];
export type ObservationDetail = components["schemas"]["ObservationDetailResponse"];
export type ObservationTag = components["schemas"]["ObservationTagResponse"];
export interface Area { id: number; code: string; name: string }
export interface Child { id: number; name: string; classroom_id: number }
export interface IndicatorOption {
  indicator_code: string;
  indicator_name: string;
  dimension: string;
  level: number;
  level_label: string;
  description: string;
  has_quant_rule: boolean;
}
export interface ObservationUpdate {
  child_id?: number | null;
  note?: string | null;
  purpose?: string | null;
  narrative?: string | null;
  analysis?: string | null;
  strategy?: string | null;
}
export interface Media {
  id: number;
  duration_sec?: number | null;
  stored_filename: string;
  content_type: string;
  size: number;
  observation_id?: number | null;
  thumbnail_failure_reason?: string | null;
}

export const MAX_UPLOAD_SIZE_BYTES = 200 * 1024 * 1024;
export const MAX_UPLOAD_SECONDS = 180; // 建议 1~3 分钟；超过会明显降低白描质量

const queryKeys = {
  observations: ["observations"] as const,
  areas: ["areas"] as const,
  children: ["children"] as const,
  indicators: ["indicators"] as const,
  media: ["media"] as const,
  observation: (id: number) => ["observations", id] as const,
};

export interface NarrativeGenerationResult {
  observation_id: number;
  status: "ready_for_review";
  processing_started_at: string;
  ready_at: string;
  narrative: string;
  is_mock: boolean;
  engine: string;
  notice: string;
}

export interface SuggestedIndicator {
  tag_id: number;
  indicator_code: string;
  indicator_name: string;
  level: number;
  level_desc: string;
  confidence: number;
  reason: string;
  rank: number;
}

export interface SystemDetermination {
  tag_id: number;
  indicator_code: string;
  indicator_name: string;
  level: number;
  level_desc: string;
  basis: string;
  deterministic: true;
  accepted: boolean;
}

export interface SuggestTagsResult {
  observation_id: number;
  suggestions: SuggestedIndicator[];
  quant_hits: SystemDetermination[];
  is_mock: boolean;
}

function ensureArray<T>(data: unknown, resourceName: string): T[] {
  if (!Array.isArray(data)) throw new Error(`${resourceName}返回格式不正确`);
  return data as T[];
}

async function getObservations() {
  const { data, error } = await apiClient.GET("/observations");
  if (error || !data) throw new Error("观察记录加载失败");
  return data;
}

async function getAreas() {
  const { data, error } = await apiClient.GET("/areas");
  if (error) throw new Error("游戏区域加载失败");
  return ensureArray<Area>(data, "游戏区域");
}

async function getChildren() {
  const { data, error } = await apiClient.GET("/children");
  if (error) throw new Error("幼儿信息加载失败");
  return ensureArray<Child>(data, "幼儿信息");
}

async function getIndicators() {
  const { data, error } = await apiClient.GET("/indicators");
  if (error) throw new Error("指标字典加载失败");
  return ensureArray<IndicatorOption>(data, "指标字典");
}

async function getMedia() {
  const { data, error } = await apiClient.GET("/media");
  if (error) throw new Error("素材信息加载失败");
  return ensureArray<Media>(data, "素材信息");
}

async function getObservation(id: number) {
  const { data, error } = await apiClient.GET("/observations/{obs_id}", {
    params: { path: { obs_id: id } },
  });
  if (error || !data) throw new Error("这条记录暂时加载失败");
  return data;
}

export function useTodayMediaData() {
  const observations = useQuery({ queryKey: queryKeys.observations, queryFn: getObservations });
  const areas = useQuery({ queryKey: queryKeys.areas, queryFn: getAreas });
  const children = useQuery({ queryKey: queryKeys.children, queryFn: getChildren });
  const media = useQuery({ queryKey: queryKeys.media, queryFn: getMedia });
  return { observations, areas, children, media };
}

export interface ObservationSearchFilters {
  /** 幼儿：主幼儿或关联幼儿命中都会返回 */
  child_id?: number;
  /** 游戏区域 */
  area_id?: number;
  status?: Observation["status"];
  /** 观察日期（北京时间）起，含当天，YYYY-MM-DD */
  date_from?: string;
  /** 观察日期（北京时间）止，含当天，YYYY-MM-DD */
  date_to?: string;
  /** 已采纳的观察指标编码 */
  indicator_code?: string;
}

const OBSERVATION_PAGE_SIZE = 20;

/** 把检索条件转成 GET /observations 的查询参数；空条件不发送。 */
export function observationSearchParams(
  filters: ObservationSearchFilters,
  offset = 0,
) {
  return {
    ...(filters.child_id != null ? { child_id: filters.child_id } : {}),
    ...(filters.area_id != null ? { area_id: filters.area_id } : {}),
    ...(filters.status ? { status: filters.status } : {}),
    ...(filters.date_from ? { date_from: filters.date_from } : {}),
    ...(filters.date_to ? { date_to: filters.date_to } : {}),
    ...(filters.indicator_code ? { indicator_code: filters.indicator_code } : {}),
    limit: OBSERVATION_PAGE_SIZE,
    offset,
  };
}

export function useObservationSearch(filters: ObservationSearchFilters) {
  const query = useInfiniteQuery({
    queryKey: [...queryKeys.observations, "search", filters],
    initialPageParam: 0,
    queryFn: async ({ pageParam }) => {
      const { data, error } = await apiClient.GET("/observations", {
        params: { query: observationSearchParams(filters, pageParam) },
      });
      if (error || !data) throw new Error("观察记录加载失败");
      return data;
    },
    getNextPageParam: (lastPage, pages) => (
      lastPage.length === OBSERVATION_PAGE_SIZE
        ? pages.reduce((count, page) => count + page.length, 0)
        : undefined
    ),
  });
  return {
    ...query,
    data: query.data?.pages.flat(),
  };
}

export function useAllMedia() {
  return useQuery({ queryKey: queryKeys.media, queryFn: getMedia });
}

export function useAreas() {
  return useQuery({ queryKey: queryKeys.areas, queryFn: getAreas });
}

export function useChildren() {
  return useQuery({ queryKey: queryKeys.children, queryFn: getChildren });
}

export function useIndicators() {
  return useQuery({ queryKey: queryKeys.indicators, queryFn: getIndicators });
}

export function useObservation(id: number) {
  return useQuery({
    enabled: Number.isInteger(id) && id > 0,
    queryKey: queryKeys.observation(id),
    queryFn: () => getObservation(id),
    refetchOnMount: "always",
    refetchInterval: (query) => (
      query.state.data?.status === "processing" ? 3000 : false
    ),
  });
}

function updateObservationStatus(
  queryClient: ReturnType<typeof useQueryClient>,
  id: number,
  status: Observation["status"],
) {
  queryClient.setQueryData<ObservationDetail>(queryKeys.observation(id), (current) => (
    current ? { ...current, status } : current
  ));
  queryClient.setQueryData<Observation[]>(queryKeys.observations, (current) => (
    current?.map((item) => item.id === id ? { ...item, status } : item)
  ));
}

export function useGenerateNarrative(id: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (mode: "focused" | "explore" = "focused") => {
      const { data, error } = await apiClient.POST("/observations/{obs_id}/narrative", {
        params: { path: { obs_id: id }, query: { mode } },
      });
      if (error || !data) throw new CaptureError("这次没有整理成功，请重新试一次");
      return data as NarrativeGenerationResult;
    },
    onMutate: () => updateObservationStatus(queryClient, id, "processing"),
    onSuccess: (result) => {
      if (result.is_mock) {
        sessionStorage.setItem(`narrative-is-mock:${id}`, "true");
      } else {
        // 已用真实模型生成：清掉历史遗留的 mock 标记，避免页面误显示"尚未接入真实 AI"。
        sessionStorage.removeItem(`narrative-is-mock:${id}`);
      }
      updateObservationStatus(queryClient, id, result.status);
    },
    onSettled: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.observation(id) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.observations }),
      ]);
    },
  });
}

export function useUpdateObservation(id: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: ObservationUpdate) => {
      const { data, error } = await apiClient.PATCH("/observations/{obs_id}", {
        params: { path: { obs_id: id } },
        body,
      });
      if (error || !data) throw new Error("这次修改暂时没有保存成功");
      return data as Observation;
    },
    onMutate: async (body) => {
      await queryClient.cancelQueries({ queryKey: queryKeys.observation(id) });
      const previous = queryClient.getQueryData<ObservationDetail>(queryKeys.observation(id));
      const previousList = queryClient.getQueryData<Observation[]>(queryKeys.observations);
      queryClient.setQueryData<ObservationDetail>(queryKeys.observation(id), (current) => (
        current ? { ...current, ...body } : current
      ));
      queryClient.setQueryData<Observation[]>(queryKeys.observations, (current) => (
        current?.map((item) => item.id === id ? { ...item, ...body } : item)
      ));
      return { previous, previousList };
    },
    onError: (_error, _body, context) => {
      if (context?.previous) {
        queryClient.setQueryData(queryKeys.observation(id), context.previous);
      }
      if (context?.previousList) {
        queryClient.setQueryData(queryKeys.observations, context.previousList);
      }
    },
    onSuccess: async (saved) => {
      queryClient.setQueryData<ObservationDetail>(queryKeys.observation(id), (current) => (
        current ? { ...current, ...saved } : current
      ));
      queryClient.setQueryData<Observation[]>(queryKeys.observations, (current) => (
        current?.map((item) => item.id === id ? { ...item, ...saved } : item)
      ));
      await queryClient.invalidateQueries({ queryKey: queryKeys.observation(id) });
    },
  });
}

export function useDeleteObservation(id: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const { error } = await apiClient.DELETE("/observations/{obs_id}", {
        params: { path: { obs_id: id } },
      });
      if (error) throw new Error("这条记录没有删除成功");
    },
    onSuccess: () => {
      queryClient.removeQueries({ queryKey: queryKeys.observation(id) });
      queryClient.invalidateQueries({ queryKey: queryKeys.observations });
    },
  });
}

export function useReplaceObservationChildren(id: number) {
  const queryClient = useQueryClient();
  const [views, setViews] = useState<Record<number, SelectionState>>({});
  const queue = useMemo(() => createSelectionQueue(
    async (childIds) => {
      const { data, error } = await apiClient.PUT("/observations/{obs_id}/children", {
        params: { path: { obs_id: id } }, body: { child_ids: childIds },
      });
      if (error || !data) throw new Error("观察对象没有保存成功");
    },
    async () => {
      // 只在一批选择完成后读取详情；下一步需要新的主体和上下文失效状态。
      await queryClient.invalidateQueries({ queryKey: queryKeys.observation(id), refetchType: "all" }, { throwOnError: true });
      void queryClient.invalidateQueries({ queryKey: queryKeys.observations });
    },
    (state) => setViews((current) => ({ ...current, [id]: state })),
  ), [id, queryClient]);
  const state: SelectionState = views[id] ?? { isPending: false, isError: false };
  return { ...state, mutate: queue.select, retry: queue.retry, flush: queue.flush };
}

export function useSuggestTags(id: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const { data, error } = await apiClient.POST("/observations/{obs_id}/suggest-tags", {
        params: { path: { obs_id: id } },
      });
      if (error || !data) throw new Error("候选指标暂时没有生成成功");
      return data as SuggestTagsResult;
    },
    onSuccess: (result) => {
      if (result.is_mock) sessionStorage.setItem(`tags-are-mock:${id}`, "true");
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.observation(id) });
    },
  });
}

export interface AnalysisSuggestion {
  observation_id: number;
  analysis: string;
  strategy: string;
  is_mock: boolean;
  engine: string;
  notice: string;
}

export function useSuggestAnalysis(id: number) {
  return useMutation({
    mutationFn: async () => {
      const { data, error } = await apiClient.POST("/observations/{obs_id}/suggest-analysis", {
        params: { path: { obs_id: id } },
      });
      if (error || !data) throw new Error("AI 建议暂时没有生成成功，请再试一次");
      return data as AnalysisSuggestion;
    },
  });
}

export interface PersonGroup {
  label: string;
  ref_indexes: number[];
  clues: string[];
}
export interface ObservationPeople {
  narrative: string;
  refs: { start: number; end: number; token: string; group: boolean; clue: string }[];
  people: PersonGroup[];
  method: "aliases" | "rules" | "ai";
  notice: string;
}
export interface PersonAssignment { ref_indexes: number[]; child_id: number }

export function useObservationPeople(id: number, narrative: string, enabled: boolean) {
  return useQuery({
    queryKey: ["observation-people", id, narrative],
    queryFn: () => requestJson<ObservationPeople>(`/observations/${id}/people`, {
      method: "POST", fallbackMessage: "人物整理暂时没有完成",
    }),
    enabled: enabled && Boolean(narrative.trim()),
    staleTime: Infinity,
    retry: false,
  });
}

export function useAssignObservationPeople(id: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: { narrative: string; assignments: PersonAssignment[] }) =>
      requestJson<{ narrative: string; child_ids: number[] }>(`/observations/${id}/people/assign`, {
        method: "POST", body: JSON.stringify(body), fallbackMessage: "姓名没有保存成功",
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.observation(id) }),
  });
}

export function useDecideTag(id: number) {
  const queryClient = useQueryClient();
  const pendingCount = useIsMutating({ mutationKey: ["tag-decisions", id] });
  const mutation = useMutation({
    mutationKey: ["tag-decisions", id],
    mutationFn: async ({ accepted, tagId }: { accepted: boolean; tagId: number }) => {
      const { data, error } = await apiClient.PATCH(
        "/observations/{obs_id}/tags/{tag_id}",
        {
          params: { path: { obs_id: id, tag_id: tagId } },
          body: { accepted },
        },
      );
      if (error || !data) throw new Error("这次选择没有保存成功");
      return { accepted, tagId };
    },
    onMutate: async ({ accepted, tagId }) => {
      await queryClient.cancelQueries({ queryKey: queryKeys.observation(id) });
      const previous = queryClient.getQueryData<ObservationDetail>(queryKeys.observation(id));
      queryClient.setQueryData<ObservationDetail>(queryKeys.observation(id), (current) => (
        current
          ? {
              ...current,
              tags: current.tags.map((tag) => (
                tag.id === tagId ? { ...tag, accepted } : tag
              )),
            }
          : current
      ));
      return { previous: previous?.tags.find((tag) => tag.id === tagId) };
    },
    onError: (_error, _variables, context) => {
      if (context?.previous) {
        queryClient.setQueryData<ObservationDetail>(queryKeys.observation(id), (current) => current ? { ...current, tags: current.tags.map((tag) => tag.id === context.previous?.id ? { ...tag, accepted: context.previous.accepted } : tag) } : current);
      }
    },
    onSettled: () => {
      if (queryClient.isMutating({ mutationKey: ["tag-decisions", id] }) === 1) {
        void queryClient.invalidateQueries({ queryKey: queryKeys.observation(id) });
      }
    },
  });
  return { ...mutation, isPending: pendingCount > 0 };
}

export function useAddTeacherTag(id: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ indicatorCode, level }: { indicatorCode: string; level: number }) => {
      const { data, error } = await apiClient.POST("/observations/{obs_id}/tags", {
        params: { path: { obs_id: id } },
        body: { indicator_code: indicatorCode, level },
      });
      if (error || !data) throw new Error("补充指标暂时没有保存成功");
      return data as ObservationTag;
    },
    onSuccess: (tag) => {
      queryClient.setQueryData<ObservationDetail>(queryKeys.observation(id), (current) => (
        current ? { ...current, tags: [...current.tags, tag] } : current
      ));
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.observation(id) });
    },
  });
}

interface ConfirmationResult {
  ok: boolean;
  observation: Observation;
  accepted_tag_count: number;
}

export function useConfirmObservation(id: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const { data, error } = await apiClient.POST("/observations/{obs_id}/confirm", {
        params: { path: { obs_id: id } },
      });
      if (error || !data) throw new Error("这条记录暂时没有确认成功");
      return data as ConfirmationResult;
    },
    onSuccess: (result) => {
      queryClient.setQueryData<ObservationDetail>(queryKeys.observation(id), (current) => (
        current ? { ...current, ...result.observation } : current
      ));
      queryClient.setQueryData<Observation[]>(queryKeys.observations, (current) => (
        current?.map((item) => (
          item.id === id ? { ...item, ...result.observation } : item
        ))
      ));
      void queryClient.invalidateQueries({ queryKey: queryKeys.observations });
    },
  });
}

interface CaptureProgress { observationId?: number }
interface CaptureInput {
  file: File;
  areaId: number;
  progress: CaptureProgress;
  onUploadProgress: (percentage: number) => void;
}

export class CaptureError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "CaptureError";
  }
}

function getId(data: unknown, step: string): number {
  if (!data || typeof data !== "object" || !("id" in data) || typeof data.id !== "number") {
    throw new CaptureError(`${step}没有完成，请点按钮重试`);
  }
  return data.id;
}

function uploadErrorMessage(status?: number) {
  if (status === 413) return "文件太大了，最多 200MB。可以拍短一点的视频";
  if (status === 400) return "只支持照片和视频（JPG、PNG、HEIC、MP4、MOV）";
  if (status === 422) return "视频太长了，建议录 1~3 分钟的片段。超过 3 分钟会影响生成效果，请缩短后再上传";
  return "上传失败，点这里重试";
}

function uploadFile(
  file: File,
  observationId: number,
  onProgress: (percentage: number) => void,
) {
  return new Promise<number>((resolve, reject) => {
    const request = new XMLHttpRequest();
    const formData = new FormData();
    formData.append("file", file);

    request.open("POST", `/api/uploads?observation_id=${observationId}`);
    const token = readToken();
    if (token) request.setRequestHeader("Authorization", `Bearer ${token}`);
    request.upload.addEventListener("progress", (event) => {
      if (event.lengthComputable) {
        onProgress(Math.min(100, Math.round((event.loaded / event.total) * 100)));
      }
    });
    request.addEventListener("load", () => {
      if (request.status < 200 || request.status >= 300) {
        reject(new CaptureError(uploadErrorMessage(request.status)));
        return;
      }
      try {
        onProgress(100);
        resolve(getId(JSON.parse(request.responseText), "素材上传"));
      } catch {
        reject(new CaptureError("素材上传没有完成，请点按钮重试"));
      }
    });
    request.addEventListener("error", () => reject(new CaptureError(uploadErrorMessage())));
    request.addEventListener("abort", () => reject(new CaptureError(uploadErrorMessage())));
    request.send(formData);
  });
}

async function submitCapture({ file, areaId, progress, onUploadProgress }: CaptureInput) {
  if (!progress.observationId) {
    let observationResult;
    try {
      observationResult = await apiClient.POST("/observations", {
        body: { area_id: areaId },
      });
    } catch {
      throw new CaptureError("记录没有建好，点这里重试");
    }
    if (observationResult.error || !observationResult.data) {
      throw new CaptureError("记录没有建好，点这里重试");
    }
    progress.observationId = getId(observationResult.data, "观察记录");
  }

  try {
    onUploadProgress(0);
    await uploadFile(file, progress.observationId, onUploadProgress);
  } catch (error) {
    try {
      await requestJson<void>(`/observations/${progress.observationId}`, {
        method: "DELETE",
        fallbackMessage: "空记录清理失败",
      });
    } catch {
      // 上传失败仍保留原错误；服务端只会留下无素材草稿，不会暴露他人数据。
    }
    progress.observationId = undefined;
    if (error instanceof CaptureError) throw error;
    throw new CaptureError("上传失败，点这里重试");
  }

  return { observationId: progress.observationId };
}

export function getMediaFileUrl(mediaId: number) {
  return `/api/media/${mediaId}/file`;
}

export function getMediaThumbnailUrl(mediaId: number) {
  return `/api/media/${mediaId}/thumbnail`;
}

export function getObservationExportUrl(observationId: number, includeIndicators: boolean) {
  return `/api/observations/${observationId}/export?include_indicators=${includeIndicators}`;
}

export interface ExportedObservationFile {
  blob: Blob;
  fileName: string;
  size: number;
}

function exportFileName(response: Response) {
  const disposition = response.headers.get("Content-Disposition") ?? "";
  const encodedName = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
  if (encodedName) {
    try {
      return decodeURIComponent(encodedName);
    } catch {
      // Fall through to the ASCII filename when the header is malformed.
    }
  }
  return disposition.match(/filename="?([^";]+)"?/i)?.[1] ?? "observation.docx";
}

export async function fetchObservationExport(
  observationId: number,
  includeIndicators: boolean,
): Promise<ExportedObservationFile> {
  const response = await fetch(getObservationExportUrl(observationId, includeIndicators));
  if (!response.ok) throw new Error("Word 文档暂时没有导出成功");
  const blob = await response.blob();
  return { blob, fileName: exportFileName(response), size: blob.size };
}

export function getMonthlyExportUrl(year: number, month: number, includeIndicators: boolean) {
  const params = new URLSearchParams({
    year: String(year),
    month: String(month),
    include_indicators: String(includeIndicators),
  });
  return `/api/exports/monthly?${params.toString()}`;
}

export function useSubmitCapture() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: submitCapture,
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.observations }),
        queryClient.invalidateQueries({ queryKey: queryKeys.media }),
      ]);
    },
  });
}
