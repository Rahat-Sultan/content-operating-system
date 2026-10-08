"use client";

import { ApiKeysSection } from "../parts";
import { VaultGate } from "@/components/VaultGate";

export default function ApiKeysPage() {
  return (
    <VaultGate>
      <ApiKeysSection />
    </VaultGate>
  );
}
