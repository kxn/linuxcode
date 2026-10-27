/* Declarations used by the open-source trust daemon but absent from Darling's
 * incomplete headers. No implementations or runtime behavior are supplied. */
#ifdef __OBJC__
#import <Foundation/Foundation.h>
#import <MobileAsset/MobileAsset.h>
@interface MAAsset (LinuxcodeTrustdDeclarations)
- (NSURL *)getLocalFileUrl;
- (void)purge:(void (^)(MAPurgeResult))completion;
- (id)assetProperty:(NSString *)name;
+ (void)startCatalogDownload:(NSString *)type options:(MADownloadOptions *)options then:(void (^)(MADownLoadResult))completion;
- (void)startDownload:(MADownloadOptions *)options then:(void (^)(MADownLoadResult))completion;
@end
@interface MAAssetQuery (LinuxcodeTrustdDeclarations)
- (void)augmentResultsWithState:(BOOL)enabled;
@end
@interface NSURLSession (LinuxcodeTrustdDeclarations)
+ (void)_obliterateAllBackgroundSessionsWithCompletionHandler:(void (^)(void))completion;
@end
@interface NSURLSessionConfiguration (LinuxcodeTrustdDeclarations)
+ (instancetype)backgroundSessionConfigurationWithIdentifier:(NSString *)identifier;
@end
@interface NSCharacterSet (LinuxcodeTrustdDeclarations)
+ (instancetype)URLPathAllowedCharacterSet;
@end
@interface NSString (LinuxcodeTrustdDeclarations)
- (NSString *)stringByAddingPercentEncodingWithAllowedCharacters:(NSCharacterSet *)characters;
@end
@interface NSDictionary (LinuxcodeTrustdDeclarations)
- (BOOL)writeToURL:(NSURL *)url error:(NSError **)error;
@end
#endif
