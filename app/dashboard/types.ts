export interface PipelineProgress {
  stage: string;
  message: string;
  current: number;
  total: number;
  percent: number;
}

export interface ScoutInfo {
  name: string;
  signalCount: number;
  generatedAt: string;
  requiresKey: boolean;
}
