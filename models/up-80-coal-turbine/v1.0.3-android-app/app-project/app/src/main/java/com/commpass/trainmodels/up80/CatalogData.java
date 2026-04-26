package com.commpass.trainmodels.up80;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

final class CatalogData {
    String version;
    String sourceVersion;
    String manufacturingReleaseUrl;
    String manufacturingZipUrl;
    String repoFolderUrl;
    String chassisPartsDocUrl;
    final List<CatalogItem> parts = new ArrayList<>();
    final Map<String, CatalogItem> byId = new HashMap<>();
    final Map<String, float[]> shellOffsets = new HashMap<>();
}
