import * as Crypto from "expo-crypto";
import * as Network from "expo-network";

import type { AppDeps } from "./state/AppContext";
import { openSqliteStore } from "./storage/sqlite";
import { secureTokenStore } from "./storage/secureToken";

const reachable = (s: Network.NetworkState) => Boolean(s.isConnected) && s.isInternetReachable !== false;

export async function createDeviceDeps(): Promise<AppDeps> {
  return {
    store: await openSqliteStore(),
    tokens: secureTokenStore,
    newId: () => Crypto.randomUUID(),
    isDeviceOnline: async () => reachable(await Network.getNetworkStateAsync()),
    onDeviceOnlineChange: (listener) => {
      const subscription = Network.addNetworkStateListener((s) => listener(reachable(s)));
      return () => subscription.remove();
    },
  };
}
