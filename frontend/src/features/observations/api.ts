import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiClient } from "../../api/client";
import type { components } from "../../api/generated/schema";

export type Observation = components["schemas"]["ObservationResponse"];
export interface Area { id: number; code: string; name: string }
export interface Child { id: number; name: string; classroom_id: number }
export interface Media {
  id: number;
  stored_filename: string;
  content_type: string;
  size: number;
  observation_id?: number | null;
}

const queryKeys = {
  observations: ["observations"] as const,
  areas: ["areas"] as const,
  children: ["children"] as const,
  media: ["media"] as const,
};

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

async function getMedia() {
  const { data, error } = await apiClient.GET("/media");
  if (error) throw new Error("素材信息加载失败");
  return ensureArray<Media>(data, "素材信息");
}

export function useTodayMediaData() {
  const observations = useQuery({ queryKey: queryKeys.observations, queryFn: getObservations });
  const areas = useQuery({ queryKey: queryKeys.areas, queryFn: getAreas });
  const children = useQuery({ queryKey: queryKeys.children, queryFn: getChildren });
  const media = useQuery({ queryKey: queryKeys.media, queryFn: getMedia });
  return { observations, areas, children, media };
}

export function useAreas() {
  return useQuery({ queryKey: queryKeys.areas, queryFn: getAreas });
}

interface CaptureProgress { mediaId?: number; observationId?: number }
interface CaptureInput { file: File; areaId: number; progress: CaptureProgress }

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
  if (status === 413) return "文件太大了，最多 20MB。可以拍短一点的视频";
  if (status === 400) return "只支持 JPG、PNG 和 MP4";
  return "上传失败，点这里重试";
}

async function submitCapture({ file, areaId, progress }: CaptureInput) {
  if (!progress.mediaId) {
    const formData = new FormData();
    formData.append("file", file);
    let uploadResult;
    try {
      uploadResult = await apiClient.POST("/uploads", {
        body: { file: file.name },
        bodySerializer: () => formData,
      });
    } catch {
      throw new CaptureError(uploadErrorMessage());
    }
    if (uploadResult.error || !uploadResult.data) {
      throw new CaptureError(uploadErrorMessage(uploadResult.response.status));
    }
    progress.mediaId = getId(uploadResult.data, "素材上传");
  }

  if (!progress.observationId) {
    let observationResult;
    try {
      observationResult = await apiClient.POST("/observations", { body: { area_id: areaId } });
    } catch {
      throw new CaptureError("记录没有建好，点这里重试");
    }
    if (observationResult.error || !observationResult.data) {
      throw new CaptureError("记录没有建好，点这里重试");
    }
    progress.observationId = getId(observationResult.data, "观察记录");
  }

  try {
    const attachResult = await apiClient.POST("/observations/{obs_id}/attach-media", {
      params: {
        path: { obs_id: progress.observationId },
        query: { media_id: progress.mediaId },
      },
    });
    if (attachResult.error) throw new CaptureError("素材还没关联好，点这里重试");
  } catch (error) {
    if (error instanceof CaptureError) throw error;
    throw new CaptureError("素材还没关联好，点这里重试");
  }

  return { observationId: progress.observationId };
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
