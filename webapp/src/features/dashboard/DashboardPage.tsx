import { useEffect, useMemo, useState } from "react";
import { DetectionCard } from "../../components/DetectionCard";
import { HardwareFaultCard } from "../../components/HardwareFaultCard";
import { PoseRegistryPanel } from "../../components/PoseRegistryPanel";
import { RuntimeConfigPanel } from "../../components/RuntimeConfigPanel";
import { SafetyAlert } from "../../components/SafetyAlert";
import { StatusBar } from "../../components/StatusBar";
import { VideoPanel } from "../../components/VideoPanel";
import { WorkflowPanel } from "../../components/WorkflowPanel";
import { isMockMode } from "../../api/client";
import { getDropPoses, getTaskPoses, recordDropPose, recordTaskPose } from "../../api/poses";
import { getRuntimeConfig, updateRuntimeConfig } from "../../api/runtimeConfig";
import { moveHome, moveStandby, moveWork, runFakeGrasp, startFollow, stopFollow, stopWorkflow } from "../../api/workflow";
import { DEFAULT_RUNTIME_CONFIG } from "../runtime-config/runtimeConfigSchema";
import { useApiAction } from "../../hooks/useApiAction";
import { useDetectionPolling } from "../../hooks/useDetectionPolling";
import { useStatusPolling } from "../../hooks/useStatusPolling";
import type { DropPosesResponse, RuntimeConfig, TaskPosesResponse } from "../../types/domain";
import { canRunFakeGrasp, hasRequiredDropPoses, hasRequiredTaskPoses, listMissingRequirements } from "../../state/uiStore";

export function DashboardPage() {
  const { status, error: statusError } = useStatusPolling();
  const { detection, error: detectionError } = useDetectionPolling();
  const { run, pending, lastError } = useApiAction();
  const [runtimeConfig, setRuntimeConfig] = useState<RuntimeConfig>(DEFAULT_RUNTIME_CONFIG);
  const [taskPoses, setTaskPoses] = useState<TaskPosesResponse | null>(null);
  const [dropPoses, setDropPoses] = useState<DropPosesResponse | null>(null);

  useEffect(() => {
    void (async () => {
      const [runtimeResp, taskResp, dropResp] = await Promise.all([getRuntimeConfig(), getTaskPoses(), getDropPoses()]);
      if (runtimeResp.ok && runtimeResp.data) setRuntimeConfig(runtimeResp.data);
      if (taskResp.ok && taskResp.data) setTaskPoses(taskResp.data);
      if (dropResp.ok && dropResp.data) setDropPoses(dropResp.data);
    })();
  }, []);

  const missing = useMemo(() => listMissingRequirements(taskPoses, dropPoses), [taskPoses, dropPoses]);
  const fakeGraspEnabled = canRunFakeGrasp(status, taskPoses, dropPoses);
  const followEnabled = Boolean(status && status.can_up && !status.busy && status.current_mode !== "running_fake_cycle");

  async function handleApplyConfig() {
    const response = await run(() => updateRuntimeConfig(runtimeConfig));
    if (!response?.ok) {
      window.alert(buildErrorMessage(response?.message, response?.code));
    }
  }

  async function handleRecordTask(name: "home" | "work" | "standby") {
    const oldValue = taskPoses?.task_poses[name]?.pose;
    const confirmText = oldValue
      ? `当前 ${name} 已存在：\n${oldValue.join(", ")}\n\n是否覆盖？`
      : `确认记录 ${name} 位姿？`;
    if (!window.confirm(confirmText)) return;
    const response = await run(() => recordTaskPose(name, true));
    if (response?.ok && response.data) {
      setTaskPoses(response.data);
    } else {
      window.alert(buildErrorMessage(response?.message, response?.code));
    }
  }

  async function handleRecordDrop(name: "bottle" | "cup") {
    const oldValue = dropPoses?.drop_poses[name]?.xy;
    const confirmText = oldValue
      ? `当前 ${name} drop 已存在：\n${oldValue.join(", ")}\n\n是否覆盖？`
      : `确认记录 ${name} drop XY？`;
    if (!window.confirm(confirmText)) return;
    const response = await run(() => recordDropPose(name, true));
    if (response?.ok && response.data) {
      setDropPoses(response.data);
    } else {
      window.alert(buildErrorMessage(response?.message, response?.code));
    }
  }

  async function handleRunFakeGrasp() {
    if (!window.confirm("确认执行一次完整 Fake Grasp 流程？")) return;
    const response = await run(() => runFakeGrasp(runtimeConfig));
    if (!response?.ok) window.alert(buildErrorMessage(response?.message, response?.code));
  }

  async function handleStartFollow() {
    const response = await run(() => startFollow(runtimeConfig));
    if (!response?.ok) window.alert(buildErrorMessage(response?.message, response?.code));
  }

  async function handleSimpleAction(action: () => Promise<unknown>) {
    const response = await run(action);
    if (!response?.ok) window.alert(buildErrorMessage(response?.message, response?.code));
  }

  const combinedError = lastError ?? statusError ?? detectionError;

  return (
    <main className="min-h-screen p-4 md:p-6">
      <StatusBar status={status} isMock={isMockMode()} />

      <div className="mt-6 grid gap-6 xl:grid-cols-[1.15fr_1fr_0.95fr]">
        <div className="space-y-6">
          <VideoPanel />
          <DetectionCard detection={detection} />
        </div>

        <div className="space-y-6">
          <WorkflowPanel
            currentStep={status?.current_step ?? null}
            busy={Boolean(status?.busy || pending)}
            canRunFakeGrasp={fakeGraspEnabled}
            canStartFollow={followEnabled}
            onMoveHome={() => void handleSimpleAction(moveHome)}
            onMoveWork={() => void handleSimpleAction(moveWork)}
            onMoveStandby={() => void handleSimpleAction(moveStandby)}
            onRunFakeGrasp={() => void handleRunFakeGrasp()}
            onStartFollow={() => void handleStartFollow()}
            onStopFollow={() => void handleSimpleAction(stopFollow)}
            onStopTask={() => void handleSimpleAction(stopWorkflow)}
          />
        </div>

        <div className="space-y-6">
          <RuntimeConfigPanel config={runtimeConfig} onChange={setRuntimeConfig} onApply={() => void handleApplyConfig()} disabled={Boolean(status?.busy || pending)} />
          <PoseRegistryPanel taskPoses={taskPoses} dropPoses={dropPoses} onRecordTask={(name) => void handleRecordTask(name)} onRecordDrop={(name) => void handleRecordDrop(name)} />
        </div>
      </div>

      <div className="mt-6 grid gap-4 xl:grid-cols-2">
        {!status?.can_up ? <HardwareFaultCard /> : null}
        {missing.length > 0 ? (
          <SafetyAlert title="配置不完整" message={`以下配置缺失，Fake Grasp 将保持禁用：${missing.join(" / ")}`} />
        ) : null}
        {combinedError ? <SafetyAlert title="接口异常" message={combinedError} /> : null}
        {status && !hasRequiredTaskPoses(taskPoses) && !hasRequiredDropPoses(dropPoses) ? null : status ? (
          <SafetyAlert
            title="安全规则"
            message={`后端必须保留末端 z >= ${status.safety.min_z_m.toFixed(2)}m 的安全限制。收到 MIN_Z_BLOCKED 时，前端只提示，不绕过。`}
          />
        ) : null}
      </div>
    </main>
  );
}

function buildErrorMessage(message?: string, code?: string) {
  if (!message && !code) return "操作失败";
  return [message ?? "操作失败", code ? `错误码: ${code}` : ""].filter(Boolean).join("\n");
}
