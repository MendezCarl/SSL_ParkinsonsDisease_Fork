import contract from '../../../shared/keypoint-contract.json';

export type KeypointModel = 'hands' | 'pose';
export type DetectionKind = 'hand' | 'pose';

export type KeypointLandmark = {
  x: number;
  y: number;
  z?: number;
  visibility?: number;
};

export type KeypointDetection = {
  kind: DetectionKind;
  label?: string | null;
  landmarks: KeypointLandmark[];
};

export type KeypointPayload = {
  model: KeypointModel;
  detections: KeypointDetection[];
};

export const EXPECTED_LANDMARKS: Record<KeypointModel, number> = {
  hands: contract.models.hands.expectedLandmarks,
  pose: contract.models.pose.expectedLandmarks,
};

export const HAND_CONNECTION_CHAINS = contract.models.hands.connections;

export const POSE_CONNECTIONS = contract.models.pose.connections;

export function primaryDetection(
  payload: KeypointPayload,
  kind: DetectionKind
): KeypointDetection | null {
  return payload.detections.find((detection) => detection.kind === kind) ?? null;
}
