--- before_pass
+++ after_pass
@@ -17,7 +17,7 @@ control I(inout metadata_t meta) {
             {
                 h_0.b = 32w2;
             }
-            if (!h_0.isValid() && false || h_0.isValid() && true && 32w2 == 32w1) 
+            if (!h_0.isValid() && false || h_0.isValid() && true && false) 
                 h_0.setValid();
         }
     }